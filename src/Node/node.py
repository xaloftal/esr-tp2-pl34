# File: src/Node/node.py
import sys
import os
import threading
import time
import uuid
from enum import Enum
import json
import socket
import copy

from control_server import ControlServer
from control_client import ControlClient

# Import shared TCP port
from config import NODE_TCP_PORT, BOOTSTRAPPER_PORT, NODE_RTP_PORT, HEARTBEAT_INTERVAL, FAIL_TIMEOUT, MAX_FAILS

# Import Message class
from aux_files.aux_message import Message, MsgType
from aux_files.RtpPacket import RtpPacket
from aux_files.colors import (
    Colors, topology_log, flood_log, stream_log, rtp_log,
    error_log, warning_log, route_log, rtp_forward_log
)

class Node:
    """
    The "brain" of the node. Maintains state (neighbors, routes)
    and defines the message processing logic.
    """

    def __init__(self, node_id, node_ip, bootstrapper_ip, is_server=False, video=None):

        self.node_id = node_id
        self.node_ip = node_ip
        self.last_alive = {}     # dictionary: {ip : timestamp}
        self.fail_count = {}     # dictionary: {ip : number of failures}
        self.last_hop = {}       # dictionary: {ip : last_hop_ip}
        self.leave_cache = set()
        self.join_cache = set()
        self.flood_cache = set()
        self.network_ready = False
        self.bootstrapper_ip = bootstrapper_ip
        self.video = video
        self.downstream_clients = {}
        self.pending_requests = []  # List of requested videos not yet received
        self.rtp_port = NODE_RTP_PORT
        self.open_rtp_port()

        # Variables to detect RTP silence
        self.last_rtp_time = {}  # {video: timestamp}
        self.rtp_timeout = 5.0   # 5 seconds without RTP to deactivate route

        # Server flag
        self.is_server = is_server

        print(topology_log(
            f"[{self.node_id}] Tipo: {'Servidor de Stream' if self.is_server else 'Nó Intermédio'}")
        )

        # Stage 1 Status: Overlay Topology
        self.neighbors = {}  # {ip: is_active}
        self.register_and_join(self.node_ip)

        # All nodes have a control server
        self.server = ControlServer(
            host_ip=self.node_ip,
            handler_callback=self.handle_incoming_message,
            video=video
        )

        # Stage 2 Status: Routes
        self.routing_table = {}
        self.flood_cache = set()
        self.lock = threading.Lock()

        self.ping_cache = set()              # Ping IDs already seen
        self.ping_reverse_path = {}          # ping_id -> previous_hop_ip
        self.last_flood_timestamp = {}       # {video: {src_ip: last_ts}}
        self.packet_loss_stats = {}          # {video: {src_ip: {"expected": X, "received": Y}}}

    def start(self):
        """Starts all node services."""

        # Stage 1: Start control server
        self.server.start()

        t = threading.Thread(target=self.heartbeat, daemon=True)
        t.start()

        # Start RTP silence detection thread
        threading.Thread(target=self.check_rtp_silence, daemon=True).start()

        # Start periodic flood if this node is the streaming server
        if self.is_server:
            threading.Thread(target=self.periodic_flood, daemon=True).start()

        print(topology_log(
            f"[{self.node_id}] Nó iniciado. Vizinhos: {self.neighbors}"
        ))

    def register_and_join(self, node_ip):
        """
        Stage 1: Registers the node with the bootstrapper
        and retrieves the neighbor list.
        """
        print(topology_log(f"[Cliente] A tentar registar com o IP: {node_ip}"))

        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(5.0)
            client.connect((self.bootstrapper_ip, BOOTSTRAPPER_PORT))

            print(topology_log(
                f"[Cliente] Ligado ao Bootstrapper em {self.bootstrapper_ip}:{BOOTSTRAPPER_PORT}"
            ))

            message = Message.create_register_message(node_ip, self.bootstrapper_ip)
            client.sendall(message.to_bytes())

            response_raw = client.recv(4096).decode()
            client.close()

            data = Message.from_json(response_raw)
            if not data:
                print(error_log(
                    f"[Cliente] Falha ao parsear resposta do bootstrapper: {response_raw}"
                ))
                return []

            neighbors = data.get_payload().get("neighbours", [])

            print(topology_log(
                f"[Cliente] Vizinhos recebidos do bootstrapper: {neighbors}"
            ))

            # Send JOIN to check if neighbors are active
            for neigh in neighbors:
                join_msg = Message.create_join_message(node_ip, neigh)
                active = self.send_tcp_message(neigh, join_msg)
                self.neighbors[neigh] = True if active else False

        except json.JSONDecodeError:
            print(error_log(
                f"[Cliente] Falha ao parsear resposta do bootstrapper: {response_raw}"
            ))
        except Exception as e:
            print(error_log(
                f"[Cliente] Erro ao conectar/registrar com o bootstrapper: {e}"
            ))

    def periodic_flood(self):
        """Executes start_flood periodically every 30 seconds."""
        print(flood_log(
            f"[{self.node_id}] FLOOD periódico ativado. Intervalo: 30 segundos."
        ))

        time.sleep(5)

        while True:
            time.sleep(30)
            self.start_flood()

    def send_tcp_message(self, dest_ip, message):
        """
        Sends a control message (Message object) to a neighboring node.
        """
        try:
            msg = (
                message.to_bytes()
                if isinstance(message, Message)
                else Message.from_dict(message).to_bytes()
            )

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(2.0)
                sock.connect((dest_ip, NODE_TCP_PORT))
                sock.sendall(msg)

            return True

        except:
            return

    def handle_incoming_message(self, msg):
        """Processes incoming TCP messages."""
        if not self.network_ready:
            self.network_ready = True

        msg_type = msg.get_type() if isinstance(msg, Message) else msg.get("type")
        msg_sender = msg.get_src() if isinstance(msg, Message) else msg.get("srcip")

        if msg_type == MsgType.FLOOD:
            with self.lock:
                if self.neighbors.get(msg_sender) is False:
                    self.neighbors[msg_sender] = True
                    self.last_alive[msg_sender] = time.time()
                    self.fail_count[msg_sender] = 0
                    print(topology_log(
                        f"[{self.node_id}] Vizinho {msg_sender} reativado via FLOOD."
                    ))

            self.handle_flood_message(msg)

        elif msg_type == MsgType.ALIVE:
            with self.lock:
                self.last_alive[msg_sender] = time.time()
                self.fail_count[msg_sender] = 0

        elif msg_type == MsgType.LEAVE:
            self.handle_leave_message(msg)

        elif msg_type == MsgType.JOIN:
            self.handle_join_message(msg)

        elif msg_type == MsgType.STREAM_START:
            self.handle_stream_start(msg)

        elif msg_type == MsgType.PING_TEST:
            self.handle_pingtest_message(msg)

        else:
            print(warning_log(
                f"[{self.node_id}] Tipo de mensagem desconhecida: {msg_type}"
            ))

    def handle_flood_message(self, msg):
        """
        Dynamically processes FLOOD messages.
        """
        src_ip = msg.get_src()
        msg_id = msg.id
        payload = msg.get_payload()

        hop_count = payload.get("hop_count", 0)
        video = payload.get("video")
        start_ts = payload.get("start_timestamp", time.time())
        origin_ip = payload.get("origin_ip", src_ip)

        accum_latency_prev = payload.get("accumulated_latency", 0)
        accum_jitter_prev = payload.get("accumulated_jitter", 0)
        accum_loss_prev = payload.get("accumulated_loss", 0)

        if self.is_server:
            if self.server.video == video:
                return

        current_latency_total = (time.time() - start_ts) * 1000
        current_latency_hop = max(
            current_latency_total - accum_latency_prev, 0.0
        )

        if video not in self.last_flood_timestamp:
            self.last_flood_timestamp[video] = {}

        old_ts = self.last_flood_timestamp[video].get(src_ip)
        jitter_hop = abs(current_latency_total - old_ts) if old_ts else 0
        self.last_flood_timestamp[video][src_ip] = current_latency_total

        stats = self.packet_loss_stats.get(video, {}).get(
            src_ip, {"expected": 1, "received": 1}
        )
        loss_rate_hop = 1 - (stats["received"] / max(stats["expected"], 1))

        new_accum_latency = accum_latency_prev + current_latency_hop
        new_accum_jitter = accum_jitter_prev + jitter_hop
        new_accum_loss = accum_loss_prev + loss_rate_hop

        α, β, γ, δ = 50, 1, 0.5, 300
        score = (
            (hop_count + 1) * α +
            new_accum_latency * β +
            new_accum_jitter * γ +
            new_accum_loss * δ
        )

        if src_ip != self.node_ip and origin_ip != self.node_ip and video:
            new_route = {
                "next_hop": src_ip,
                "hop": hop_count + 1,
                "latency": new_accum_latency,
                "jitter": new_accum_jitter,
                "loss": new_accum_loss,
                "score": score,
                "is_active": False
            }

            with self.lock:
                self.routing_table.setdefault(video, [])
                existing = next(
                    (r for r in self.routing_table[video]
                     if r["next_hop"] == src_ip),
                    None
                )

                if existing:
                    new_route["is_active"] = existing["is_active"]
                    existing.update(new_route)
                else:
                    self.routing_table[video].append(new_route)

        # 6. OPTIMIZATION
        has_clients = (video in self.downstream_clients and len(self.downstream_clients[video]) > 0)
        if video in self.routing_table and has_clients:
            self._attempt_route_optimization(video)

        # 7. RE-BROADCAST
        key = (origin_ip, msg_id)
        with self.lock:
            if key in self.flood_cache:
                return
            self.flood_cache.add(key)

        new_msg = Message.create_flood_message(
            srcip=self.node_ip,
            origin_flood=origin_ip,
            flood_id=msg_id,
            hop_count=hop_count + 1,
            video=video,
            start_timestamp=start_ts,
            accumulated_latency=new_accum_latency,
            accumulated_jitter=new_accum_jitter,
            accumulated_loss=new_accum_loss
        )

        for neigh, is_active in self.neighbors.items():
            if neigh != src_ip and is_active:
                self.send_tcp_message(neigh, new_msg)

    def _attempt_route_optimization(self, video):
        """
        Helper function to check if a better route exists and perform the switch (handover).
        """
        # 1. Find the best available neighbor right now
        best_neigh_ip = self.find_best_active_neighbour(video)
        if not best_neigh_ip:
            return

        with self.lock:
            # Identify current active route
            current_active_route = next(
                (r for r in self.routing_table[video] if r["is_active"]), None
            )
            old_ip = current_active_route["next_hop"] if current_active_route else None

            # If the best route is already active, do nothing
            if old_ip == best_neigh_ip:
                return

            # Get route objects to compare scores
            best_route_obj = next(
                (r for r in self.routing_table[video] if r["next_hop"] == best_neigh_ip), None
            )

            # HYSTERESIS
            # Only switch if the new route is significantly better (e.g., < 90% of current score)
            # This avoids constant switching when values are very similar (ping-pong effect)
            if current_active_route:
                current_score = current_active_route["score"]
                new_score = best_route_obj["score"]

                print(f"\n[OTIMIZAÇÃO DA DEPURAÇÃO] Comparação para {video}")
                print(f"Rota atual [{current_active_route['next_hop']}]: Score = {current_score:.2f}")
                print(f"Candidato     [{best_route_obj['next_hop']}]: Score = {new_score:.2f}")

                threshold = current_score * 0.90
                print(f"Limiar de comutação (90% da corrente): {threshold:.2f}")

                if new_score > threshold:
                    print(
                        f"DECISÃO: Manter a rota atual. "
                        f"({new_score:.2f} > {threshold:.2f}) -> Melhoria insuficiente."
                    )
                    return
                else:
                    print(
                        f"DECISÃO: TROCA! "
                        f"({new_score:.2f} <= {threshold:.2f}) -> Melhoria significativa."
                    )

            print(route_log(
                f"[{self.node_id}] Otimização encontrada! Comutando {old_ip} -> {best_neigh_ip}"
            ))

            # Execute switch (make-before-break)

            # 1. Activate new route locally
            best_route_obj["is_active"] = True

            # 2. Request stream from the new neighbor
            start_msg = Message.create_stream_start_message(
                self.node_ip, best_neigh_ip, video
            )
            self.send_tcp_message(best_neigh_ip, start_msg)

            # 3. Schedule teardown of the old route
            if old_ip:
                current_active_route["is_active"] = False
                threading.Thread(
                    target=self._delayed_teardown,
                    args=(old_ip, video),
                    daemon=True
                ).start()

    def _delayed_teardown(self, old_ip, video):
        """
        Waits briefly to ensure the new stream arrives before cutting the old one.
        """
        time.sleep(1.0)  # 1 second overlap
        try:
            print(stream_log(
                f"[{self.node_id}] Enviando TEARDOWN atrasado para {old_ip}"
            ))
            teardown_msg = Message.create_teardown_message(
                self.node_ip, old_ip, video
            )
            self.send_tcp_message(old_ip, teardown_msg)
        except Exception as e:
            print(f"Teardown error: {e}")

    def announce_leave(self):
        """
        Announces to neighbors that this node is leaving and cleans up active streams.
        """
        print(warning_log(f"[{self.node_id}] Anunciando LEAVE..."))

        # New stream cleanup logic
        if self.video in self.routing_table:
            active_route = next(
                (r for r in self.routing_table[self.video] if r["is_active"]), None
            )

            if active_route:
                upstream_ip = active_route["next_hop"]
                print(stream_log(
                    f"[{self.node_id}] Envio do TEARDOWN para o upstream ativo ({upstream_ip})."
                ))

                teardown_msg = Message.create_teardown_message(
                    srcip=self.node_ip,
                    destip=upstream_ip,
                    video=self.video
                )
                self.send_tcp_message(upstream_ip, teardown_msg)
            else:
                print(warning_log(
                    f"[{self.node_id}] Não existe uma rota ATIVA para {self. video} enviar TEARDOWN."
                ))

        # Original logic: send LEAVE to neighbors for topology update
        for neigh_ip, is_active in self.neighbors.items():
            if is_active:
                msg = Message.create_leave_message(self.node_ip, neigh_ip)
                self.send_tcp_message(neigh_ip, msg)

        time.sleep(0.2)

    def handle_leave_message(self, msg):
        """
        Processes a received LEAVE message.
        """
        dead_ip = msg.get_src() if isinstance(msg, Message) else msg.get("srcip")

        if dead_ip in self.leave_cache:
            return
        self.leave_cache.add(dead_ip)

        self.join_cache.discard(dead_ip)

        print(route_log(
            f"[{self.node_id}] Vizinho {dead_ip} saiu da rota."
        ))

        with self.lock:
            # Mark neighbor as inactive instead of removing
            if dead_ip in self.neighbors:
                self.neighbors[dead_ip] = False
                print(route_log(
                    f"[{self.node_id}] Vizinho {dead_ip} marcado como inativo."
                ))
                self.join_cache.discard(dead_ip)
                self.leave_cache.add(dead_ip)

            # Deactivate all routes that use this next hop
            for video, routes in self.routing_table.items():
                for route in routes:
                    if route["next_hop"] == dead_ip:
                        route["is_active"] = False
                        print(route_log(
                            f"[{self.node_id}] Rota desativada: fluxo {video}, via{dead_ip}"
                        ))

                # Remove dead neighbor from downstream clients
                if video in self.downstream_clients and dead_ip in self.downstream_clients[video]:
                    self.downstream_clients[video].remove(dead_ip)
                    print(route_log(
                        f"[{self.node_id}] Cliente a jusante {dead_ip} removido de {video} (SAÍDA)."
                    ))

    def start_overlay_probe(self, video_name):
        """
        (Server only) Starts a PING to test the active route of a video.
        """
        if not self.is_server:
            print(f"[{self.node_id}] Erro: Apenas o servidor pode iniciar o comando PING.")
            return

        if video_name not in self.downstream_clients or not self.downstream_clients[video_name]:
            print(
                f"[{self.node_id}] PING abortado: Sem espectadores para '{video_name}' (Rota inativa)."
            )
            return

        print(f"[{self.node_id}] Iniciando PING/Traceroute para '{video_name}'...")

        initial_path = [self.node_id]

        for child_ip in self.downstream_clients[video_name]:
            msg = Message.create_pingtest_message(
                srcip=self.node_ip,
                destip=child_ip,
                video_name=video_name,
                current_path=initial_path
            )
            self.send_tcp_message(child_ip, msg)

    def handle_pingtest_message(self, msg):
        """
        Processes the PING: logs passage, updates path, and forwards if downstream clients exist.
        """
        payload = msg.get_payload()
        video_name = payload.get("video")
        path_so_far = payload.get("path", [])

        new_path = path_so_far + [self.node_id]

        print(
            f"[{self.node_id}] PING recebido! Rota atual: {' -> '.join(new_path)}"
        )

        destinations = self.downstream_clients.get(video_name, [])
        if destinations:
            msg_clone = copy.deepcopy(msg)
            msg_clone.payload["path"] = new_path

            for child_ip in destinations:
                self.send_tcp_message(child_ip, msg_clone)

    def handle_join_message(self, msg):
        neigh_ip = msg.get_src() if isinstance(msg, Message) else msg.get("srcip")

        if neigh_ip in self.join_cache:
            return
        self.join_cache.add(neigh_ip)
        self.leave_cache.discard(neigh_ip)

        print(route_log(
            f"[{self.node_id}] Neighbor {neigh_ip} joined the network."
        ))

        with self.lock:
            # Reactivate neighbor
            self.neighbors[neigh_ip] = True
            print(route_log(
                f"[{self.node_id}] Neighbor {neigh_ip} marked as active (JOIN)."
            ))

            # Reset heartbeat
            self.last_alive[neigh_ip] = time.time()
            self.fail_count[neigh_ip] = 0

            # Deactivate routes using this next hop (will be recalculated)
            for video, routes in self.routing_table.items():
                for route in routes:
                    if route["next_hop"] == neigh_ip:
                        route["is_active"] = False

                        


        
    def handle_stream_start(self, msg):
        msg_sender = msg.get_src() if isinstance(msg, Message) else msg.get("srcip")
        msg_payload = msg.get_payload() if isinstance(msg, Message) else msg.get("payload", {})
        video = msg_payload.get("video", None)
        
        if not video:
            print(error_log(f"[{self.node_id}] STREAM_START sem nome de vídeo. Ignorar."))
            return
        
        # --- SERVER LOGIC ---
        if self.is_server:
            # Check if server has this video
            has_video = False
            if isinstance(self.server.video, dict):
                has_video = video in self.server.video
            elif isinstance(self.server.video, str):
                has_video = (self.server.video == video)
            
            if has_video:
                if video not in self.downstream_clients:
                    self.downstream_clients[video] = []
                
                if msg_sender not in self.downstream_clients[video]:
                    self.downstream_clients[video].append(msg_sender)
                print(stream_log(f"[{self.node_id}] Pedido de stream {video} recebido de {msg_sender}. A iniciar envio..."))
                self.server.start_stream_to_client(msg_sender, video)
            else:
                print(error_log(f"[{self.node_id}] Pedido de stream {video} recebido de {msg_sender}, mas vídeo não disponível."))
        # ROUTER LOGIC
        else:
            
            print(stream_log(f"[{self.node_id}] Pedido de stream START recebido de {msg_sender} para vídeo {video}."))
            
            # Restarting the HEARTBEAT TIMER of the node requesting the stream
            # If the node you are sending to (msg_sender) was inactive, this START serves as an ALIVE.
            with self.lock:
                self.last_alive[msg_sender] = time.time()
                self.fail_count[msg_sender] = 0
                if msg_sender in self.neighbors:
                    self.neighbors[msg_sender] = True # Ensures the neighbor is active
            
            # Add clients to the downstream
            if video not in self.downstream_clients:
                self.downstream_clients[video] = []
            if msg_sender not in self.downstream_clients[video]:
                self.downstream_clients[video].append(msg_sender)
                print(stream_log(f"[{self.node_id}] Cliente {msg_sender} adicionado à lista de distribuição de {video}."))
            
            # Check if the route is ALREADY active (Stream already running)
            route_activate = False
            if video in self.routing_table:
                for route in self.routing_table[video]:
                    if route["is_active"]:
                        route_activate = True
                        break
            
            if route_activate:
                print(stream_log(f"[{self.node_id}] O vídeo {video} já está a ser recebido. Não é preciso pedir ao vizinho."))
                return
            
            # Check if we have a route to request the stream
            if video not in self.routing_table:
                print(warning_log(f"[{self.node_id}] Nenhuma rota conhecida para o vídeo {video}."))
                return
            
            best_neigh = self.find_best_active_neighbour(video)
            
            if best_neigh:
                
                #Add to a "pending" list to avoid request spam.
                if video not in self.pending_requests:
                   self.pending_requests.append(video)

                print(stream_log(f"[{self.node_id}] A reenviar pedido de stream START para {best_neigh} para vídeo {video}."))
                
                # Enable the route to this blocked neighbor
                with self.lock:
                    if video in self.routing_table:
                        for route in self.routing_table[video]:
                            if route["next_hop"] == best_neigh:
                                route["is_active"] = True
                                print(route_log(f"[{self.node_id}] Rota ATIVADA para '{video}' via {best_neigh} (STREAM_START enviado)"))
                                break
                
                forward_msg = Message.create_stream_start_message(
                    srcip=self.node_ip,
                    destip=best_neigh,
                    video=video
                )

                self.send_tcp_message(best_neigh, forward_msg)

            else:
                print(warning_log(f"[{self.node_id}] Nenhum vizinho encontrado para reenviar pedido de stream START para vídeo {video}.")) 
             

               
    def stream_start_handler(self, video):
        if video not in self.routing_table:
            print(warning_log(f"[{self.node_id}] Nenhuma rota conhecida para o vídeo {video}."))
            return

        best_neigh = self.find_best_active_neighbour(video)

        if best_neigh:
            print(stream_log(f"[{self.node_id}] A pedir stream START ao vizinho {best_neigh} para o vídeo {video}."))
            
            start_msg = Message.create_stream_start_message(
                srcip=self.node_ip,
                destip=best_neigh,
                video=video
            )
            self.send_tcp_message(best_neigh, start_msg)
        else:
            print(warning_log(f"[{self.node_id}] Nenhum vizinho ativo encontrado para o vídeo {video}."))

    def start_flood(self):
        """
        Initiate a flood from this node (server or client).
        """
        # Create a unique ID for the flood
        msg_id = str(uuid.uuid4())

       # Save to cache (to avoid receiving the same flood again)
        key = (self.node_ip, msg_id)
        with self.lock:
            self.flood_cache.add(key)

        # Create a flood message
        flood_msg = Message.create_flood_message(
            srcip=self.node_ip,
            origin_flood=self.node_ip,
            flood_id=msg_id,
            hop_count=0,
            video=self.video
        )

        # Send the flood ONLY to active neighbors
        for neigh_ip, is_active in self.neighbors.items():
            if is_active:
                print(flood_log(f"[{self.node_id}] A iniciar FLOOD com ID {msg_id} para stream {self.video}"))
                print(flood_log(f"[{self.node_id}] A enviar FLOOD para {neigh_ip}"))
                self.send_tcp_message(neigh_ip, flood_msg)
                


    def local_leave_cleanup(self, dead_ip):
        """
        Mark neighbor as dead.
        If this neighbor was our "next_hop" for any active video, try changing route!
        """
        with self.lock:
            # Cache and Neighbor Cleanup
            self.join_cache.discard(dead_ip)
            self.leave_cache.add(dead_ip)
            
            if dead_ip in self.neighbors:
                self.neighbors[dead_ip] = False
                print(route_log(f"[{self.node_id}] Vizinho {dead_ip} marcado como inativo (TIMEOUT)."))

           # Checking Affected Routes
            for video, routes in self.routing_table.items():
                
                active_route_died = False
                for route in routes:
                    # If the route used this neighbor AND was active
                    if route["next_hop"] == dead_ip and route["is_active"]:
                        route["is_active"] = False
                        active_route_died = True
                        print(error_log(f"[{self.node_id}] Rota ATIVA para {video} morreu (via {dead_ip})!"))
                
                # Remove the dead neighbor from the downstream customer list.
                if video in self.downstream_clients and dead_ip in self.downstream_clients[video]:
                    self.downstream_clients[video].remove(dead_ip)
                    print(route_log(f"[{self.node_id}] Cliente downstream {dead_ip} removido de {video} (nó morto)."))
                
                # FAILOVER LOGIC
                # If we lose the active route AND we have customers waiting (downstream)    
                has_clients = (video in self.downstream_clients and len(self.downstream_clients[video]) > 0)
                
                if active_route_died and has_clients:
                    print(warning_log(f"[{self.node_id}] A procurar rota alternativa de emergência para {video}..."))
                    
                    # Find the next best neighbor (who isn't dead)
                    best_neigh = self.find_best_active_neighbour(video)
                    
                    if best_neigh:
                        print(route_log(f"[{self.node_id}] Rota alternativa encontrada! A pedir a {best_neigh}."))

                        # Pre-activate the route to avoid packet rejection (orphan packets)
                        if video in self.routing_table:
                            for r in self.routing_table[video]:
                                if r["next_hop"] == best_neigh:
                                    r["is_active"] = True
                                    print(route_log(f"[{self.node_id}] Rota de emergência ativada localmente via {best_neigh}"))
                                    break
                        
                        # Send START request to the new neighbor.
                        start_msg = Message.create_stream_start_message(
                            srcip=self.node_ip,
                            destip=best_neigh,
                            video=video
                        )
                        self.send_tcp_message(best_neigh, start_msg)
                        
                        # Add to pendants to avoid immediate duplicates
                        if video not in self.pending_requests:
                            self.pending_requests.append(video)
                    else:
                        print(error_log(f"[{self.node_id}] CRÍTICO: Sem rotas alternativas para {video}. Stream vai parar."))


    def heartbeat(self):
        while True:
            time.sleep(HEARTBEAT_INTERVAL)
            now = time.time()

            for neigh, is_active in list(self.neighbors.items()):
                # Only send ALIVE to active neighbors
                if not is_active:
                    continue

                # Send silent ALIVE
                self.send_tcp_message(neigh, Message.create_alive_message(self.node_ip, neigh))

                # First time — create initial timestamp
                if neigh not in self.last_alive:
                    self.last_alive[neigh] = now

                # If too much time has passed without response → increase failures
                if now - self.last_alive[neigh] > FAIL_TIMEOUT:
                    self.fail_count[neigh] = self.fail_count.get(neigh, 0) + 1
                else:
                    self.fail_count[neigh] = 0

                # If it failed multiple times → consider dead
                if self.fail_count[neigh] >= MAX_FAILS:
                    print(error_log(f"[{self.node_id}] Vizinho {neigh} desapareceu."))
                    self.local_leave_cleanup(neigh)
                    self.last_alive.pop(neigh, None)
                    self.fail_count.pop(neigh, None)


                    
    def find_best_active_neighbour(self, video, exclude_ip=None):
        """
        Selects the active neighbor with the best metric.
        AUTOMATICALLY EXCLUDES:
        1. The explicitly provided 'exclude_ip' (optional).
        2. Any node that is already my client (downstream) for this video.
        """
        if video not in self.routing_table:
            return None

        # List of clients that are already receiving this video from me (MY CHILDREN)
        # If I request from my child, I create a loop!
        my_children = self.downstream_clients.get(video, [])

        active_routes = []
        for r in self.routing_table[video]:
            neigh_ip = r["next_hop"]
            
            # Check if it is physically active (TCP/Neighbors)
            # Confirms whether self.neighbors returns True/False or an object.
            # If it is a state dictionary: self.neighbors.get(neigh_ip, False) works if the value is boolean.
            is_online = self.neighbors.get(neigh_ip, False)
            
            # Check if it was explicitly excluded
            not_excluded_arg = (neigh_ip != exclude_ip)

            # Check if it is my client (Anti-loop protection)
            not_my_child = (neigh_ip not in my_children)
            
            if is_online and not_excluded_arg and not_my_child:
                active_routes.append(r)

        if not active_routes:
            return None

        # Choose the one with the lowest score
        best = min(active_routes, key=lambda r: r["score"])
        return best["next_hop"]



    def open_rtp_port(self):
        """Creates the UDP socket and starts the listening thread."""

        try:
            self.rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.rtp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.rtp_socket.bind((self.node_ip, self.rtp_port))
            
            print(topology_log(
                f"[{self.node_id}] À escuta de RTP (UDP) no {self.node_ip}:{self.rtp_port}"
            ))

            # Thread to avoid blocking the rest of the program
            threading.Thread(
                target=self.listen_rtp_thread,
                daemon=True
            ).start()
        except Exception as e:
            print(error_log(
                f"[{self.node_id}] Erro ao abrir socket RTP: {e}"
            ))

    def listen_rtp_thread(self):
        """Loop that continuously receives UDP packets."""
        while True:
            try:
                # Receive raw data (bytes) and sender address
                data, address = self.rtp_socket.recvfrom(20480)
                
                if data:
                    sender_ip = address[0]
                    
                    # Extract video name from RTP packet payload
                    rtp = RtpPacket()
                    rtp.decode(data)
                    video_name = rtp.getVideoName()
                    
                    if not video_name:
                        print(error_log(
                            f"[{self.node_id}] RTP packet sem nome de vídeo. Ignorar."
                        ))
                        continue

                    self.handle_rtp_packet(data, video_name, sender_ip)

            except Exception as e:
                print(error_log(
                    f"[{self.node_id}] Erro na thread RTP: {e}"
                ))
                import traceback
                traceback.print_exc()
                break



    def handle_rtp_packet(self, raw_data, video_name, sender_ip):
        """
        1. Checks if there is an active route for this video.
        2. If so → forwards to the neighbor on the active route.
        3. Updates statistics and timers.
        """
        
        # Safety check - video_name should never be None
        if not video_name:
            print(error_log(
                f"[{self.node_id}] ERRO: handle_rtp_packet recebeu video_name=None. Ignorar pacote."
            ))
            return

        # 0. Decode RTP packet
        rtp = RtpPacket()
        rtp.decode(raw_data)
        current_seq = rtp.seqNum()

        # 1. Update packet loss statistics
        if video_name not in self.packet_loss_stats:
            self.packet_loss_stats[video_name] = {}

        if sender_ip not in self.packet_loss_stats[video_name]:
            # First packet — initialize
            self.packet_loss_stats[video_name][sender_ip] = {
                "expected": 1,
                "received": 1,
                "last_seq": current_seq
            }
        else:
            stats = self.packet_loss_stats[video_name][sender_ip]
            last_seq = stats["last_seq"]

            if current_seq > last_seq:
                missing = current_seq - last_seq - 1
                if missing < 0:
                    missing = 0
                stats["expected"] += 1 + missing
                stats["received"] += 1
                stats["last_seq"] = current_seq
            else:
                # Duplicate, out-of-order, etc.
                stats["expected"] += 1

        # 2. Update RTP timer
        if hasattr(self, 'last_rtp_time'):
            self.last_rtp_time[video_name] = time.time()

        # 3. Pending request cleanup
        if video_name in self.pending_requests:
            self.pending_requests.remove(video_name)

        # 4. Check if there is an active route for this video
        active_route = None
        if video_name in self.routing_table:
            for route in self.routing_table[video_name]:
                if route["is_active"] and route["next_hop"] == sender_ip:
                    active_route = route
                    break
        
        # If there is no active route from this sender, ignore packet
        if not active_route:
            # Build route info for debug logging
            routes_info = ""
            if video_name in self.routing_table:
                routes_info = f" Rotas: {[(r['next_hop'], r['is_active']) for r in self.routing_table[video_name]]}"
            
            # Check if this is an orphan packet (arrived without request)
            if not hasattr(self, 'orphan_count'):
                self.orphan_count = {}
            
            key = (video_name, sender_ip)
            if key not in self.orphan_count:
                self.orphan_count[key] = 0
            
            self.orphan_count[key] += 1
            
            if self.orphan_count[key] <= 3:
                print(warning_log(
                    f"[{self.node_id}] Pacote RTP para '{video_name}' seq={current_seq} de {sender_ip} sem rota ativa. Ignorar.{routes_info}"
                ))
            
            # If too many orphan packets are received, send TEARDOWN
            if self.orphan_count[key] > 10:
                print(warning_log(
                    f"[{self.node_id}] ATENÇÃO: Limite de órfãos atingido. A forçar TEARDOWN para {sender_ip}."
                ))
                
                teardown_msg = Message.create_teardown_message(
                    srcip=self.node_ip, 
                    destip=sender_ip,
                    video=video_name
                )
                threading.Thread(
                    target=self.send_tcp_message,
                    args=(sender_ip, teardown_msg),
                    daemon=True
                ).start()
                
                self.orphan_count[key] = 0 
            
            return

        # Reset orphan counter on valid packet
        if hasattr(self, 'orphan_count'):
            key = (video_name, sender_ip)
            if key in self.orphan_count:
                self.orphan_count[key] = 0

        # 5. Check if there are downstream clients requesting the video
        has_clients = (
            video_name in self.downstream_clients and
            len(self.downstream_clients[video_name]) > 0
        )

        if not has_clients:
            # No downstream clients, but an active route still exists
            # This can happen if the last client left but RTP is still arriving
            print(warning_log(
                f"[{self.node_id}] RTP recebido para '{video_name}' mas sem clientes downstream. Enviar TEARDOWN para {sender_ip}."
            ))
            
            # Deactivate route
            active_route["is_active"] = False
            
            # Send TEARDOWN upstream
            teardown_msg = Message.create_teardown_message(
                srcip=self.node_ip, 
                destip=sender_ip,
                video=video_name
            )
            threading.Thread(
                target=self.send_tcp_message,
                args=(sender_ip, teardown_msg),
                daemon=True
            ).start()
            return

        # 6. Forward RTP to downstream clients
        for client_ip in self.downstream_clients[video_name]:
            self.rtp_socket.sendto(raw_data, (client_ip, self.rtp_port))
    
    def check_rtp_silence(self):
        """Checks RTP silence and performs failover ignoring the current route."""
        while True:
            time.sleep(1)
            now = time.time()
            
            # PHASE 1: Detect failures (INSIDE LOCK)
            failover_actions = [] 

            with self.lock:
                # Use list() to create a copy and avoid iteration errors
                for video, last_ts in list(self.last_rtp_time.items()):
                    if now - last_ts > self.rtp_timeout:
                        print(warning_log(
                            f"[{self.node_id}] ALERTA: Silêncio RTP em {video}."
                        ))
                        
                        failed_ip = None
                        # Deactivate current route
                        for route in self.routing_table.get(video, []):
                            if route["is_active"]:
                                route["is_active"] = False
                                failed_ip = route["next_hop"]
                                print(error_log(
                                    f"[{self.node_id}] Rota falhou via {failed_ip}"
                                ))
                        
                        self.last_rtp_time.pop(video, None)
                        
                        # Store data to attempt failover
                        has_clients = (
                            video in self.downstream_clients and
                            self.downstream_clients[video]
                        )
                        if failed_ip and has_clients:
                            failover_actions.append((video, failed_ip))

            # PHASE 2: Execute failover
            for video, failed_ip in failover_actions:
                with self.lock:
                    print(warning_log(
                        f"[{self.node_id}] A procurar alternativa (exceto {failed_ip})..."
                    ))
                    best_neigh = self.find_best_active_neighbour(
                        video, exclude_ip=failed_ip
                    )
                    
                    # Reactivate failed route if no alternative exists
                    if not best_neigh and failed_ip:
                        print(warning_log(
                            f"[{self.node_id}] Sem alternativa. A tentar reativar a rota falhada ({failed_ip})..."
                        ))
                        best_neigh = failed_ip

                    if best_neigh:
                        # 1. Pre-activate route
                        route_obj = None
                        if video in self.routing_table:
                            for r in self.routing_table[video]:
                                if r["next_hop"] == best_neigh:
                                    r["is_active"] = True
                                    route_obj = r
                                    print(route_log(
                                        f"[{self.node_id}] Rota pré-ativada via {best_neigh}"
                                    ))
                                    break
                        
                        # 2. Try sending START
                        try:
                            start_msg = Message.create_stream_start_message(
                                srcip=self.node_ip,
                                destip=best_neigh,
                                video=video
                            )
                            self.send_tcp_message(best_neigh, start_msg)
                            print(route_log(
                                f"[{self.node_id}] START enviado com sucesso para {best_neigh}"
                            ))

                        except Exception as e:
                            # 3. ROLLBACK: deactivate route immediately if START fails
                            print(error_log(
                                f"[{self.node_id}] Falha ao enviar START para {best_neigh}: {e}"
                            ))
                            if route_obj:
                                route_obj["is_active"] = False
                    else:
                        print(error_log(
                            f"[{self.node_id}] Nenhuma outra rota disponível."
                        ))

    def activate_route(self, video, neighbor_ip):
        """Marks the route as active only if the neighbor is active."""

        # If neighbor is inactive → do NOT activate route
        if not self.neighbors.get(neighbor_ip, False):
            return

        if video in self.routing_table:
            with self.lock:
                for route in self.routing_table[video]:
                    if route["next_hop"] == neighbor_ip:
                        if not route["is_active"]:
                            route["is_active"] = True
                            print(rtp_log(
                                f"[{self.node_id}] Rota ATIVADA para {video} via {neighbor_ip} (RTP recebido)"
                            ))

    def handle_teardown(self, msg):
        sender_ip = msg.get_src()
        payload = msg.get_payload()
        video = payload.get("video")
        best_route = None  

        print(stream_log(
            f"[{self.node_id}] Recebido TEARDOWN de {sender_ip} para {video}"
        ))
        
        # KEY FIX: STOP RTP SENDING TO THIS CLIENT (sender_ip)
        # This must happen on ALL nodes, whether original streamer or intermediates.
        # Assumes stop_stream_to_client uses (sender_ip, video) as key to stop the thread.
        try:
            self.server.stop_stream_to_client(sender_ip, video)
        except Exception as e:
            print(error_log(
                f"[{self.node_id}] Erro ao parar stream RTP para {sender_ip}: {e}"
            ))
        
        # Remove client from distribution list
        if video in self.downstream_clients:
            if sender_ip in self.downstream_clients[video]:
                self.downstream_clients[video].remove(sender_ip)
                print(stream_log(
                    f"[{self.node_id}] Cliente {sender_ip} removido da lista de {video}."
                ))

            # Check if there is another client
            if len(self.downstream_clients[video]) == 0:
                print(stream_log(
                    f"[{self.node_id}] Último cliente saiu. A fechar a rota para {video}..."
                ))
                
                if video in self.routing_table:
                    for route in self.routing_table[video]:
                        if route["is_active"]:
                            route["is_active"] = False
                            best_route = route["next_hop"]
                            
                            if best_route:
                                print(stream_log(
                                    f"[{self.node_id}] A enviar TEARDOWN para cima ({best_route})."
                                ))
                                forward_msg = Message(
                                    msg_type=MsgType.TEARDOWN,
                                    srcip=self.node_ip,
                                    destip=best_route,
                                    payload={"video": video}
                                )
                                self.send_tcp_message(best_route, forward_msg)
            else:
                print(stream_log(
                    f"[{self.node_id}] Ainda restam {len(self.downstream_clients[video])} clientes. A rota mantém-se ATIVA."
                ))
        
        return best_route

    def get_next_hop_for_ping(self, previous_hop):
        """Selects an active neighbor to forward the PING, avoiding loops."""
        for neigh, active in self.neighbors.items():
            if active and neigh != previous_hop:
                return neigh
        return None


# MAIN (Entry Point)

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Uso: python3 node.py NODE_ID NODE_IP BOOTSTRAPPER_IP [--server] VIDEO")
        print("\nExemplo Servidor:")
        print("  python3 node.py streamer 10.0.0.20 10.0.20.20 --server video1.Mjpeg")
        sys.exit(1)

    node_id = sys.argv[1]
    node_ip = sys.argv[2]
    boot_ip = sys.argv[3]
    video = sys.argv[5] if len(sys.argv) > 5 else None

    is_server_flag = "--server" in sys.argv    
    
    node = Node(
        node_id, node_ip, boot_ip,
        is_server=is_server_flag,
        video=video
    )

    # Start services (Stage 1: Register and Listen)
    node.start()

    time.sleep(2)

    # Interactive command loop
    if node.is_server:
        prompt_text = (
            f"[{node.node_id}] (Servidor) Comando "
            "(flood / ping / routes / neigh / exit): \n"
        )
    else:
        prompt_text = (
            f"[{node.node_id}] (Nó)  Comando "
            "(routes / neigh / leave / exit): \n "
        )

    while True:
        try:
            cmd = input(prompt_text).strip().lower()
            
            if cmd == "flood":
                if node.is_server:
                    node.start_flood()
                else:
                    print(error_log(
                        "Erro: Apenas o servidor pode iniciar um 'flood'."
                    ))

            elif cmd == "ping":
                if node.is_server:
                    node.start_overlay_probe(video)

            elif cmd == "routes":
                print(f"[{node.node_id}] Tabela de Rotas:")
                print(json.dumps(node.routing_table, indent=4))

            elif cmd == "neigh":
                print(f"[{node.node_id}] Vizinhos: {node.neighbors}")
                
            elif cmd == "exit":
                print(f"[{node.node_id}] A sair...")
                break

            elif cmd == "leave":
                node.announce_leave()
                print(f"[{node.node_id}] LEAVE enviado. A terminar...")
                break
            
            elif cmd == "":
                print(prompt_text)
        
        except KeyboardInterrupt:
            print(f"\n[{node.node_id}] A sair...")
            break
