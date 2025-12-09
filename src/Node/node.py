# Ficheiro: src/Node/node.py
import sys
import os
import threading
import time
import uuid
from enum import Enum
import json
import socket

from control_server import ControlServer
from control_client import ControlClient
# Importa a porta TCP partilhada
from config import NODE_TCP_PORT, BOOTSTRAPPER_PORT, NODE_RTP_PORT, HEARTBEAT_INTERVAL, FAIL_TIMEOUT, MAX_FAILS
# Import Message class
from aux_files.aux_message import Message, MsgType
from aux_files.RtpPacket import RtpPacket

class Node:
    """
    O "cérebro" do nó. Mantém o estado (vizinhos, rotas) e
    define a lógica de processamento de mensagens.
    """
    
    def __init__(self, node_id, node_ip, bootstrapper_ip,  is_server=False, video=None):
        
        self.node_id = node_id
        self.node_ip = node_ip
        self.last_alive = {}     # dicionário: {ip : timestamp}
        self.fail_count = {}     # dicionário: {ip : nº de falhas}
        self.last_hop = {}      # dicionário: {ip : last_hop_ip}
        self.leave_cache = set()
        self.join_cache = set()
        self.flood_cache = set()
        self.network_ready = False
        self.bootstrapper_ip = bootstrapper_ip
        self.video = video
        self.downstream_clients = {} # 
        self.pending_requests = [] # Lista de vídeos que já pedimos mas ainda não chegaram
        self.rtp_port = NODE_RTP_PORT
        self.open_rtp_port()

        # --- NOVO: Variáveis para Detecção de Silêncio RTP ---
        self.last_rtp_time = {} # {video: timestamp}
        self.rtp_timeout = 0.5  # 2 segundos sem RTP para desativar rota
        # ---------------------------------------------------
        
       
        
         
        # --- Flag de Servidor ---
        self.is_server = is_server        
        
        
        print(f"[{self.node_id}] Tipo: {'Servidor de Stream' if self.is_server else 'Nó Intermédio'}")
        
        # --- Estado da Etapa 1: Topologia Overlay ---
        self.neighbors = {}  # {ip: is_active}
        self.register_and_join(self.node_ip)

        
        # TODOS OS NODES TÊM CONTROL SERVER
        self.server = ControlServer(
            host_ip=self.node_ip,
            handler_callback=self.handle_incoming_message,
            video=video
        )
        
        # --- Estado da Etapa 2: Rotas ---
        #print(json.dumps(node.routing_table, indent=4))
        self.routing_table = {} 
        self.flood_cache = set() # Evita loops de flood
        self.lock = threading.Lock() 
        
        self.ping_cache = set()      # ping unique ids already seen
        self.ping_reverse_path = {}  # ping_id -> previous_hop_ip   
        self.last_flood_timestamp = {}   # {video: {src_ip: last_ts}} guarda o ultimo timestamp de flood vindo do mesmo vizinho
        self.packet_loss_stats = {}   # {video: {src_ip: {"expected": X, "received": Y}}}

        
        

    def start(self):
        """Inicia todos os serviços do nó."""   

        # ETAPA 1: Iniciar o "servidor" para escutar vizinhos
        self.server.start()
        t = threading.Thread(target=self.heartbeat, daemon=True)
        t.start()

        # --- NOVO: Inicia a thread de verificação de silêncio RTP ---
        threading.Thread(target=self.check_rtp_silence, daemon=True).start()
        # ------------------------------------------------------------
        
        # --- NOVO: Iniciar FLOOD Periódico se for o Streamer ---
        if self.is_server:
            threading.Thread(target=self.periodic_flood, daemon=True).start()
        # -------------------------------------------------------

        print(f"[{self.node_id}] Nó iniciado. Vizinhos: {self.neighbors}")
        
    
    def register_and_join(self, node_ip):
        """
        ETAPA 1: Regista o nó no bootstrapper e obtém a lista de vizinhos.
        """
        print(f"[Cliente] A tentar registar com o IP: {node_ip}")
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(5.0)
            client.connect((self.bootstrapper_ip, BOOTSTRAPPER_PORT))
            print(f"[Cliente] Ligado ao Bootstrapper em {self.bootstrapper_ip}:{BOOTSTRAPPER_PORT}")

            # Envia a mensagem de registo
            message = Message.create_register_message(node_ip, self.bootstrapper_ip)
            client.sendall(message.to_bytes())

            # Recebe a resposta (JSON com a lista de vizinhos)
            response_raw = client.recv(4096).decode()
            client.close()

            data = Message.from_json(response_raw)
            if not data:
                print(f"[Cliente] Falha a parsear resposta do bootstrapper: {response_raw}")
                return []
                
            neighbors = data.get_payload().get("neighbours", [])
            
            print(f"[Cliente] Vizinhos recebidos do bootstrapper: {neighbors}")
            
            
            #
            #   Send join to know if neighbours are active or not
            #
            
            for neigh in neighbors:
                join_msg = Message.create_join_message(node_ip, neigh)

                active = self.send_tcp_message(neigh, join_msg)
                
                # if there's a connection, add the neighbour with True
                self.neighbors[neigh] = True if active else False
                       
                
        except json.JSONDecodeError:
            print(f"[Cliente] Falha a parsear resposta do bootstrapper: {response_raw}")
            return []
        except Exception as e:
            print(f"[Cliente] Erro a ligar/registar no bootstrapper: {e}")
            return []

    def periodic_flood(self):
        """Executa start_flood periodicamente, a cada 30 segundos."""
        print(f"[{self.node_id}] [FLOOD] (FLOOD) periódico foi ativado. Intervalo: 30 segundos.")
        
        # O atraso inicial evita que o flood ocorra antes de o servidor estar pronto.
        time.sleep(5) 
        
        while True:
            # Espera 30 segundos antes de cada execução
            time.sleep(30)
            
            # Chama a função existente para iniciar o flood
            # Nota: isto irá interromper o prompt de comando interativo!
            self.start_flood()


    def send_tcp_message(self, dest_ip, message):
        """
        Envia uma mensagem de controlo (Message object) para um nó vizinho.
        """
        try:
            msg = message.to_bytes() if isinstance(message, Message) else Message.from_dict(message).to_bytes()
            
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(2.0) # Timeout curto para não bloquear
                
                # Cada nó escuta na mesma porta de controlo
                sock.connect((dest_ip, NODE_TCP_PORT)) 
                sock.sendall(msg)
            return True

        except: #Exception as e:
            # print(f"[Cliente] Erro a enviar TCP para {dest_ip}:{NODE_TCP_PORT}: {e}")
            return #False
        
        

    def handle_incoming_message(self, msg):
        """Processa mensagens recebidas do TCP."""
        if not self.network_ready:
            self.network_ready = True

        msg_type = msg.get_type() if isinstance(msg, Message) else msg.get("type")
        msg_sender = msg.get_src() if isinstance(msg, Message) else msg.get("srcip")

        if msg_type == MsgType.FLOOD:
            self.handle_flood_message(msg)
        
        elif msg_type == MsgType.ALIVE:
            with self.lock:
                self.last_alive[msg_sender] = time.time()
                self.fail_count[msg_sender] = 0
            #print(f"[{self.node_id}] {msg_sender} está vivo")
        
        elif msg_type == MsgType.LEAVE:
            self.handle_leave_message(msg)
        
        elif msg_type == MsgType.JOIN:
            self.handle_join_message(msg)
            
        elif msg_type == MsgType.STREAM_START:
            self.handle_stream_start(msg)

        elif msg_type == MsgType.PING:
            print("\n" + "="*60)
            print(f"[{self.node_id}]  RECEBI PING")
            print(f"    → ID:        {msg.id}")
            print(f"    → Sender:    {msg_sender}")
            print(f"    → Origin:    {msg.get_src()}")
            print("="*60)

            # Guardar hop anterior (para rota de volta)
            self.last_hop[msg.id] = msg_sender
            print(f"[{self.node_id}] last_hop[{msg.id}] = {msg_sender}")

            # --- Se este nó é o SERVIDOR ---
            if self.is_server:
                pong = Message.create_pong_message(
                    srcip=self.node_ip,
                    destip=msg.get_src()     # o cliente final
                )
                pong.id = msg.id

                prev_hop = self.last_hop[msg.id]   # nó imediatamente anterior na rota de ida

                print(f"[{self.node_id}] Envio PONG para hop anterior {prev_hop}")
                self.send_tcp_message(prev_hop, pong)
                return

            # --- Este nó é intermédio ---
            # Reencaminhar PING para qualquer vizinho ativo, exceto quem o enviou
            for neigh, active in self.neighbors.items():
                if active and neigh != msg_sender:
                    print(f"[{self.node_id}] Forward PING {msg.id} → {neigh}")
                    self.send_tcp_message(neigh, msg)
                    return

            print(f"[{self.node_id}] Sem vizinho para reenviar PING")


        elif msg_type == MsgType.PONG:
            print("\n" + "-"*60)
            print(f"[{self.node_id}]  RECEBI PONG")
            print(f"    → ID:        {msg.id}")
            print(f"    → Sender:    {msg_sender}")
            print(f"    → Origin:    {msg.get_src()}")
            print("-"*60)

            # Guardar hop anterior também NA VOLTA
            self.last_hop[msg.id] = msg_sender
            print(f"[{self.node_id}] updated last_hop[{msg.id}] = {msg_sender}")

            # O destino FINAL (cliente) verifica se este nó é o destino final
            if self.node_ip == msg.get_dest():
                print(f"[{self.node_id}] 🎉 PONG chegou ao CLIENTE FINAL!")
                return

            # Descobrir hop seguinte (voltar para trás na rota)
            prev_hop = self.last_hop.get(msg.id)

            if prev_hop is None:
                print(f"[{self.node_id}] ERRO: last_hop sem entrada para {msg.id}")
                return

            print(f"[{self.node_id}] Forward PONG {msg.id} → {prev_hop}")
            self.send_tcp_message(prev_hop, msg)

        elif msg_type == MsgType.STREAM_START:
            self.handle_stream_start(msg)

        elif msg_type == MsgType.PING:
            ping_id = msg.id
            payload = msg.get_payload()

            origin = payload.get("origin")
            previous = payload.get("previous")

            # Evitar loops
            if ping_id in self.ping_cache:
                return
            self.ping_cache.add(ping_id)

            #guarda caminho de retorno
            self.ping_reverse_path[ping_id] = msg_sender

            print(f"[{self.node_id}] Recebi PING de {msg_sender}")

            # Se sou o servidor → enviar resposta
            if self.is_server:
                reply = Message(
                    msg_type=MsgType.PONG,
                    srcip=self.node_ip,
                    destip=msg_sender,
                    payload={"origin": origin, "previous": self.node_ip},
                    msg_id=ping_id
                )
                self.send_tcp_message(msg_sender, reply)
                print(f"[{self.node_id}] Sou servidor → PONG enviado para {msg_sender}")
                return

            # Caso contrário → reencaminhar
            for neigh, active in self.neighbors.items():
                if active and neigh != msg_sender:
                    forward_msg = Message(
                        msg_type=MsgType.PING,
                        srcip=self.node_ip,
                        destip=neigh,
                        payload={"origin": origin, "previous": self.node_ip},
                        msg_id=ping_id
                    )
                    self.send_tcp_message(neigh, forward_msg)
                    print(f"[{self.node_id}] Reencaminhei PING para {neigh}")

        elif msg_type == MsgType.PONG:
            ping_id = msg.id
            payload = msg.get_payload()

            origin = payload.get("origin")
            previous = payload.get("previous")

            print(f"[{self.node_id}] Recebi PONG de {msg_sender}")

            if self.node_ip == origin:
                print(f"[{self.node_id}] PONG FINAL RECEBIDO!")
                if hasattr(self, "gui_callback"):
                    self.gui_callback("PONG RECEBIDO")
                return


            # Obter caminho invertido
            next_hop = self.ping_reverse_path.get(ping_id)
            if next_hop:
                reply = Message(
                    msg_type=MsgType.PONG,
                    srcip=self.node_ip,
                    destip=next_hop,
                    payload={"origin": origin, "previous": self.node_ip},
                    msg_id=ping_id
                )
                self.send_tcp_message(next_hop, reply)
                print(f"[{self.node_id}] Reencaminhei PONG para {next_hop}")
            
        elif msg_type == MsgType.TEARDOWN:
            self.handle_teardown(msg)
        
        else:
            print(f"[{self.node_id}] Tipo de mensagem desconhecido: {msg_type}")
            
            

    # ------------------------------------------------------------------
    # ETAPA 2: LÓGICA DE CONSTRUÇÃO DE ROTAS (Flooding)
    # ------------------------------------------------------------------
    def handle_flood_message(self, msg):
        """
        Processa mensagens de FLOOD:
        - Atualiza rotas
        - Calcula métricas (latência, jitter, perdas)
        - Reenvia se não visto antes
        - TENTA OTIMIZAR A ROTA ATIVA SE ENCONTRAR UMA MELHOR
        """

        src_ip = msg.get_src()
        msg_id = msg.id
        payload = msg.get_payload()

        hop_count = payload.get("hop_count", 0)
        video = payload.get("video")
        start_ts = payload.get("start_timestamp", time.time())
        origin_ip = payload.get("origin_ip", src_ip)

        # ------------------ LATÊNCIA ------------------
        current_latency = (time.time() - start_ts) * 1000  # ms

        # ------------------ JITTER ------------------
        if video not in self.last_flood_timestamp:
            self.last_flood_timestamp[video] = {}

        old_ts = self.last_flood_timestamp[video].get(src_ip, None)

        if old_ts is None:
            jitter = 0
        else:
            jitter = abs(current_latency - old_ts)

        self.last_flood_timestamp[video][src_ip] = current_latency

        # ------------------ PERDAS (PACKET LOSS) ------------------
        if video not in self.packet_loss_stats:
            self.packet_loss_stats[video] = {}

        stats = self.packet_loss_stats[video].get(src_ip, {"expected": 1, "received": 1})
        loss_rate = 1 - (stats["received"] / max(stats["expected"], 1))

        # ------------------ SCORE UNIFICADO ------------------
        α = 50      # hops
        β = 1       # latência
        γ = 0.5     # jitter
        δ = 300     # perdas %

        score = hop_count*α + current_latency*β + jitter*γ + loss_rate*δ

        # ------------------ ATUALIZAR TABELA DE ROTAS ------------------
        if src_ip != self.node_ip and video:

            new_route = {
                "next_hop": src_ip,
                "hop": hop_count,
                "latency": current_latency,
                "jitter": jitter,
                "loss": loss_rate,
                "score": score,
                "is_active": False
            }

            with self.lock:
                if video not in self.routing_table:
                    self.routing_table[video] = [new_route]
                    print(f"[{self.node_id}] Nova rota {video}: via {src_ip}")
                else:
                    # Ver se rota já existe
                    existing = next((r for r in self.routing_table[video] if r["next_hop"] == src_ip), None)

                    if existing:
                        # Preservar o estado is_active se já existia
                        new_route["is_active"] = existing["is_active"]
                        existing.update(new_route)
                        # print(f"[{self.node_id}] Rota Atualizada {video}: via {src_ip} (Score: {score:.2f})")
                    else:
                        self.routing_table[video].append(new_route)
                        print(f"[{self.node_id}] Rota Extra {video}: via {src_ip}")

        # ======================================================================
        # LÓGICA DE OTIMIZAÇÃO (SWITCHOVER)
        # ======================================================================
        
        # Só faz sentido verificar se eu estou atualmente a consumir este vídeo
        has_clients = (video in self.downstream_clients and len(self.downstream_clients[video]) > 0)
        
        # Verificar se tenho uma rota ativa para este vídeo
        current_active_route = None
        if video in self.routing_table:
            for route in self.routing_table[video]:
                if route["is_active"]:
                    current_active_route = route
                    break
        
        if current_active_route and has_clients:
            # 1. Qual é o melhor vizinho AGORA (baseado nas tabelas atualizadas)?
            best_neigh_ip = self.find_best_active_neighbour(video)
            
            # Se existe um vizinho melhor E não é o que já estamos a usar
            if best_neigh_ip and best_neigh_ip != current_active_route["next_hop"]:
                
                # Vamos buscar o score da nova rota candidata
                new_score = float('inf')
                for r in self.routing_table[video]:
                    if r["next_hop"] == best_neigh_ip:
                        new_score = r["score"]
                        break
                        
                current_score = current_active_route["score"]
                
                # 2. Histerese: Só muda se for SIGNIFICATIVAMENTE melhor 
                # (ex: novo score é < 70% do atual, ou seja, 30% melhor)
                # Isto evita o efeito "ping-pong" entre rotas com qualidade semelhante.
                threshold = 0.7 
                
                if new_score < (current_score * threshold):
                    print(f"\n[{self.node_id}] OTIMIZAÇÃO DETETADA! ")
                    print(f"   Rota Atual: via {current_active_route['next_hop']} (Score: {current_score:.2f})")
                    print(f"   Nova Rota:  via {best_neigh_ip} (Score: {new_score:.2f})")
                    print(f"   -> A iniciar troca de rota...")
                    
                    # A. Pedir stream ao novo vizinho (Make before Break)
                    start_msg = Message.create_stream_start_message(
                        srcip=self.node_ip, destip=best_neigh_ip, video=video
                    )
                    self.send_tcp_message(best_neigh_ip, start_msg)
                    
                    # B. Desligar o antigo (TEARDOWN)
                    old_ip = current_active_route["next_hop"]
                    teardown_msg = Message.create_teardown_message(
                        srcip=self.node_ip, destip=old_ip, video=video
                    )
                    self.send_tcp_message(old_ip, teardown_msg)
                    
                    # C. Atualizar estado local (A nova rota ficará ativa quando chegar RTP)
                    current_active_route["is_active"] = False

        # ------------------ CACHE e REBROADCAST ------------------
        key = (origin_ip, msg_id)

        with self.lock:
            if key in self.flood_cache:
                return
            self.flood_cache.add(key)

        # criar nova mensagem
        new_msg = Message.create_flood_message(
            srcip=self.node_ip,
            origin_flood=origin_ip,
            flood_id=msg_id,
            hop_count=hop_count + 1,
            video=video,
            start_timestamp=start_ts
        )

        # reenviar
        for neigh, is_active in self.neighbors.items():
            if neigh != src_ip:
                self.send_tcp_message(neigh, new_msg)
                
    def announce_leave(self):
        """
        Anuncia aos vizinhos que vai sair e limpa as streams ativas
        """
        print(f"[{self.node_id}] A anunciar LEAVE...")

        # --- NOVA LÓGICA DE LIMPEZA DE STREAMS ---
        if self.video in self.routing_table:
            # Encontrar o vizinho UPSTREAM que está a fornecer a stream (is_active=True)
            active_route = next((r for r in self.routing_table[self.video] if r["is_active"]), None)
            
            if active_route:
                upstream_ip = active_route["next_hop"]
                print(f"[{self.node_id}] Envio TEARDOWN para o upstream ativo ({upstream_ip}).")
                
                # Cria e envia a mensagem TEARDOWN
                teardown_msg = Message.create_teardown_message(
                    srcip=self.node_ip, 
                    destip=upstream_ip,
                    video=self.video
                )
                self.send_tcp_message(upstream_ip, teardown_msg)
            else:
                print(f"[{self.node_id}] Sem rota ATIVA para {self.video} para enviar TEARDOWN.")
        # --- FIM DA NOVA LÓGICA ---

        # Lógica original: Enviar LEAVE aos vizinhos para a topologia
        for neigh_ip, is_active in self.neighbors.items():
            if is_active:
                msg = Message.create_leave_message(self.node_ip, neigh_ip) 
                self.send_tcp_message(neigh_ip, msg)

        # garantir que a mensagem sai antes do processo morrer
        time.sleep(0.2)


    def handle_leave_message(self, msg):
        """
        processa mensagem LEAVE recebida
        """
        dead_ip = msg.get_src() if isinstance(msg, Message) else msg.get("srcip")

        # evitar duplicados
        if dead_ip in self.leave_cache:
            return
        self.leave_cache.add(dead_ip)
        
        # se tiver no join_cache, remover
        self.join_cache.discard(dead_ip)

        print(f"[{self.node_id}] O vizinho {dead_ip} saiu da rota.")

        with self.lock:
            # Marcar vizinho como inativo em vez de remover
            if dead_ip in self.neighbors:
                self.neighbors[dead_ip] = False
                print(f"[{self.node_id}] Vizinho {dead_ip} marcado como inativo")
                self.join_cache.discard(dead_ip)
                self.leave_cache.add(dead_ip)

            # Marcar todas as rotas que usam este next_hop como inativas
            for video, routes in self.routing_table.items():
                for route in routes:
                    if route["next_hop"] == dead_ip:
                        route["is_active"] = False
                        print(f"[{self.node_id}] Rota inativada: stream {video}, via {dead_ip}")

        # NÃO PROPAGAR LEAVE aos outros vizinhos

    def handle_join_message(self, msg):
        neigh_ip = msg.get_src() if isinstance(msg, Message) else msg.get("srcip")

        if neigh_ip in self.join_cache:
            return
        self.join_cache.add(neigh_ip)
        self.leave_cache.discard(neigh_ip)

        print(f"[{self.node_id}] O vizinho {neigh_ip} juntou-se à rede.")

        with self.lock:
            # 1. Reativar vizinho
            self.neighbors[neigh_ip] = True
            print(f"[{self.node_id}] Vizinho {neigh_ip} marcado como ativo (JOIN)")

            # 2. Reset ao heartbeat
            self.last_alive[neigh_ip] = time.time()
            self.fail_count[neigh_ip] = 0

            # 3. Reativar rotas que usam este next_hop
            for video, routes in self.routing_table.items():
                for route in routes:
                    if route["next_hop"] == neigh_ip:
                        route["is_active"] = False
                        


        
    def handle_stream_start(self, msg):
        msg_sender = msg.get_src() if isinstance(msg, Message) else msg.get("srcip")
        msg_payload = msg.get_payload() if isinstance(msg, Message) else msg.get("payload", {})
        video = msg_payload.get("video", None)
        
        # --- SERVER LOGIC ---
        if self.is_server:
            if video in self.server.video:
                print(f"[{self.node_id}] Pedido de stream {video} recebido de {msg_sender}. A iniciar envio...")
                self.server.start_stream_to_client(msg_sender, video)
            else:
                print(f"[{self.node_id}] Pedido de stream {video} recebido de {msg_sender}, mas vídeo não disponível.")
        # --- ROUTER LOGIC ---
        else:
            
            print(f"[{self.node_id}] Pedido de stream START recebido de {msg_sender} para vídeo {video}.")
            
            # 1. Add clients to the downstream
            if video not in self.downstream_clients:
                self.downstream_clients[video] = []
            if msg_sender not in self.downstream_clients[video]:
                self.downstream_clients[video].append(msg_sender)
                print(f"[{self.node_id}] Cliente {msg_sender} adicionado à lista de distribuição de {video}.")

            # 2. Verificar se a rota JÁ está ativa (Stream já a correr)
            route_activate = False
            if video in self.routing_table:
                for route in self.routing_table[video]:
                    if route["is_active"]:
                        route_activate = True
                        break
            
            if route_activate:
                print(f"[{self.node_id}] O vídeo {video} já está a ser recebido. Não é preciso pedir ao vizinho.")
                return
            
            # 3. Verificar se temos rota para pedir
            if video not in self.routing_table:
                print(f"[{self.node_id}] Nenhuma rota conhecida para o vídeo {video}.")
                return
            
            best_neigh = self.find_best_active_neighbour(video)
            
            if best_neigh:
                
                #  Adicionar a uma lista de "pendentes" para evitar spam de pedidos
                if video not in self.pending_requests:
                   self.pending_requests.append(video)

                print(f"[{self.node_id}] A reenviar pedido de stream START para {best_neigh} para vídeo {video}.")
                
                forward_msg = Message.create_stream_start_message(
                    srcip=self.node_ip,
                    destip=best_neigh,
                    video=video
                )

                self.send_tcp_message(best_neigh, forward_msg)

            else:
                print(f"[{self.node_id}] Nenhum vizinho encontrado para reenviar pedido de stream START para vídeo {video}.") 
             

               
    def stream_start_handler(self, video):
        if video not in self.routing_table:
            print(f"[{self.node_id}] Nenhuma rota conhecida para o vídeo {video}.")
            return

        best_neigh = self.find_best_active_neighbour(video)

        if best_neigh:
            print(f"[{self.node_id}] A pedir stream START ao vizinho {best_neigh} para o vídeo {video}.")
            
            start_msg = Message.create_stream_start_message(
                srcip=self.node_ip,
                destip=best_neigh,
                video=video
            )
            self.send_tcp_message(best_neigh, start_msg)
        else:
            print(f"[{self.node_id}] Nenhum vizinho ativo encontrado para o vídeo {video}.")

    def start_flood(self):
        """
        Inicia um flood a partir deste nó (servidor ou cliente).
        """
        # Criar ID único do flood
        msg_id = str(uuid.uuid4())

        # Guardar na cache (para evitar receber o mesmo flood outra vez)
        key = (self.node_ip, msg_id)
        with self.lock:
            self.flood_cache.add(key)

        # Criar mensagem de flood
        flood_msg = Message.create_flood_message(
            srcip=self.node_ip,
            origin_flood=self.node_ip,
            flood_id=msg_id,
            hop_count=0,
            video=self.video
        )

        # Enviar o flood APENAS aos vizinhos ativos
        for neigh_ip, is_active in self.neighbors.items():
            if is_active:
                print(f"[{self.node_id}] A iniciar FLOOD com ID {msg_id} para stream {self.video}")
                print(f"[{self.node_id}] Enviando FLOOD para {neigh_ip}")
                self.send_tcp_message(neigh_ip, flood_msg)
                


    def local_leave_cleanup(self, dead_ip):
        """
        1. Marca vizinho como morto.
        2. Se esse vizinho era o nosso "next_hop" para algum vídeo ativo, tenta mudar de rota!
        """
        with self.lock:
            # --- Limpeza de Cache e Vizinhos ---
            self.join_cache.discard(dead_ip)
            self.leave_cache.add(dead_ip)
            
            if dead_ip in self.neighbors:
                self.neighbors[dead_ip] = False
                print(f"[{self.node_id}] Vizinho {dead_ip} marcado como inativo (TIMEOUT).")

            # --- Verificar Rotas Afetadas ---
            for video, routes in self.routing_table.items():
                
                active_route_died = False
                for route in routes:
                    # Se a rota usava este vizinho E estava ativa
                    if route["next_hop"] == dead_ip and route["is_active"]:
                        route["is_active"] = False
                        active_route_died = True
                        print(f"[{self.node_id}] Rota ATIVA para {video} morreu (via {dead_ip})!")
                
                # --- LÓGICA DE RECUPERAÇÃO (FAILOVER) ---
                # Se perdemos a rota ativa E temos clientes à espera (downstream)
                has_clients = (video in self.downstream_clients and len(self.downstream_clients[video]) > 0)
                
                if active_route_died and has_clients:
                    print(f"[{self.node_id}] A procurar rota alternativa de emergência para {video}...")
                    
                    # 1. Encontrar o próximo melhor vizinho (que não seja o morto)
                    best_neigh = self.find_best_active_neighbour(video)
                    
                    if best_neigh:
                        print(f"[{self.node_id}] Rota alternativa encontrada! A pedir a {best_neigh}.")
                        
                        # 2. Enviar pedido START para o novo vizinho
                        start_msg = Message.create_stream_start_message(
                            srcip=self.node_ip,
                            destip=best_neigh,
                            video=video
                        )
                        self.send_tcp_message(best_neigh, start_msg)
                        
                        # (Opcional) Adicionar aos pendentes para evitar duplicados imediatos
                        if video not in self.pending_requests:
                            self.pending_requests.append(video)
                    else:
                        print(f"[{self.node_id}] CRÍTICO: Sem rotas alternativas para {video}. Stream vai parar.")
                        # Aqui poderias enviar um TEARDOWN para baixo, mas geralmente deixa-se o timeout tratar disso



    def heartbeat(self):
        while True:
            time.sleep(HEARTBEAT_INTERVAL)
            now = time.time()

            for neigh, is_active in list(self.neighbors.items()):
                # Apenas enviar ALIVE para vizinhos ativos
                if not is_active:
                    continue

                # enviar ALIVE silencioso
                self.send_tcp_message(neigh, Message.create_alive_message(self.node_ip, neigh))

                # primeira vez — criar timestamp inicial
                if neigh not in self.last_alive:
                    self.last_alive[neigh] = now

                # se passou muito tempo sem resposta → aumentar falhas
                if now - self.last_alive[neigh] > FAIL_TIMEOUT:
                    self.fail_count[neigh] = self.fail_count.get(neigh, 0) + 1
                else:
                    self.fail_count[neigh] = 0

                # se falhou várias vezes → morto
                if self.fail_count[neigh] >= MAX_FAILS:
                    print(f"[{self.node_id}] Vizinho {neigh} desapareceu.")
                    self.local_leave_cleanup(neigh)
                    self.last_alive.pop(neigh, None)
                    self.fail_count.pop(neigh, None)


                    
    def find_best_active_neighbour(self, video, exclude_ip=None):
        """
        Escolhe o vizinho ativo com a melhor métrica, IGNORANDO o 'exclude_ip'.
        """
        if video not in self.routing_table:
            return None

        active_routes = []
        for r in self.routing_table[video]:
            neigh_ip = r["next_hop"]
            
            # Verifica se está ativo nos vizinhos
            is_online = self.neighbors.get(neigh_ip, False)
            
            # Verifica se NÃO é o IP que queremos excluir
            not_excluded = (neigh_ip != exclude_ip)
            
            if is_online and not_excluded:
                active_routes.append(r)

        if not active_routes:
            return None

        # Escolhe o que tem menor score
        best = min(active_routes, key=lambda r: r["score"])
        return best["next_hop"]

    def open_rtp_port(self):
        """Cria o socket UDP e inicia a thread de escuta."""

        try:
            self.rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.rtp_socket.bind((self.node_ip, self.rtp_port))
            
            print(f"[{self.node_id}] À escuta de RTP (UDP) no {self.node_ip}:{self.rtp_port}")

            # Thread para não bloquear o resto do programa
            threading.Thread(target=self.listen_rtp_thread, daemon=True).start()
        except Exception as e:
            print(f"[{self.node_id}] Erro ao abrir socket RTP: {e}")

    def listen_rtp_thread(self):
        """Loop que recebe pacotes UDP continuamente."""
        while True:
            try:
                # Recebe dados brutos (bytes) e endereço do remetente
                data, address = self.rtp_socket.recvfrom(20480)
                
                if data:
                    sender_ip = address[0]
                    
                    # NOTA: Num sistema real, o nome do vídeo viria no pacote.
                    # Aqui, assumimos que é o vídeo que este nó está configurp«´'+do para gerir
                    # ou terias de ter lógica para extrair do header RTP.
                    current_video = self.video if self.video else "movie.Mjpeg"

                    self.handle_rtp_packet(data, current_video, sender_ip)

            except Exception as e:
                print(f"[{self.node_id}] Erro na thread RTP: {e}")
                break


    def handle_rtp_packet(self, raw_data, video_name, sender_ip):
        """
        1. Verifica se alguém quer este vídeo.
        2. Se ninguém quiser → IGNORA.
        3. Se houver clientes → ativa rota + forward.
        """

        # --------------------------------------------------------------
        # 0. Decodificar pacote RTP
        # --------------------------------------------------------------
        rtp = RtpPacket()
        rtp.decode(raw_data)
        current_seq = rtp.seqNum()

        # --------------------------------------------------------------
        # 1. Atualizar estatísticas de packet loss
        # --------------------------------------------------------------
        if video_name not in self.packet_loss_stats:
            self.packet_loss_stats[video_name] = {}

        if sender_ip not in self.packet_loss_stats[video_name]:
            # Primeiro pacote — inicializar
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
                # duplicado, fora de ordem, etc.
                stats["expected"] += 1

        # --------------------------------------------------------------
        # 2. Pending cleanup
        # --------------------------------------------------------------
        if video_name in self.pending_requests:
            self.pending_requests.remove(video_name)

        # --------------------------------------------------------------
        # 3. Verificar se alguém quer o vídeo
        # --------------------------------------------------------------
        has_clients = (
            video_name in self.downstream_clients and
            len(self.downstream_clients[video_name]) > 0
        )

        if not has_clients:
            # Novo Mecanismo de Limpeza FORÇADA (apenas para reinícios)
            if not hasattr(self, 'orphan_count'):
                self.orphan_count = {}
            
            self.orphan_count[video_name] = self.orphan_count.get(video_name, 0) + 1
            
            print(f"[{self.node_id}] Pacote órfão recebido para {video_name}. Ignorar.")
            
            # Se receber muitos pacotes órfãos (ex: 10), envia TEARDOWN forçado para o upstream.
            if self.orphan_count[video_name] > 10: 
                print(f"[{self.node_id}] ATENÇÃO: Limite de órfãos atingido. A forçar TEARDOWN para {sender_ip}.")
                
                # Enviar TEARDOWN para o nó que está a enviar o RTP (o Streamer, neste caso, 10.0.19.10)
                teardown_msg = Message.create_teardown_message(
                    srcip=self.node_ip, 
                    destip=sender_ip, # IP do Streamer
                    video=video_name
                )
                self.send_tcp_message(sender_ip, teardown_msg)
                
                # Reset do contador
                self.orphan_count[video_name] = 0 
                return
            
            return # Não faz forward, ignora o pacote

        # --------------------------------------------------------------
        # 4. Ativar rota (porque recebemos RTP válido)
        # --------------------------------------------------------------
        self.activate_route(video_name, sender_ip)
        
        # --- NOVO: ATUALIZAR O TIMER RTP APÓS RECEÇÃO VÁLIDA ---
        # Isto é a base para o Mecanismo B (check_rtp_silence)
        if hasattr(self, 'last_rtp_time'):
            self.last_rtp_time[video_name] = time.time()
        # -------------------------------------------------------

        # --------------------------------------------------------------
        # 5. Forwarding para os clientes downstream
        # --------------------------------------------------------------
        for client_ip in self.downstream_clients[video_name]:
            self.rtp_socket.sendto(raw_data, (client_ip, self.rtp_port))
        
    def check_rtp_silence(self):
        """Verifica silêncio e faz failover ignorando a rota atual."""
        while True:
            time.sleep(1)
            now = time.time()
            
            with self.lock:
                for video, last_ts in list(self.last_rtp_time.items()):
                    if now - last_ts > self.rtp_timeout:
                        print(f"[{self.node_id}] ALERTA: Silêncio RTP em {video}.")
                        
                        failed_ip = None
                        
                        # 1. Desativar rotas e descobrir quem falhou
                        for route in self.routing_table.get(video, []):
                            if route["is_active"]:
                                route["is_active"] = False
                                failed_ip = route["next_hop"] # <--- Guardar quem falhou
                                print(f"[{self.node_id}] Rota falhou via {failed_ip}")
                        
                        self.last_rtp_time.pop(video, None)

                        # 2. FAILOVER (Ignorando o failed_ip)
                        has_clients = (video in self.downstream_clients and len(self.downstream_clients[video]) > 0)
                        
                        if failed_ip and has_clients:
                            print(f"[{self.node_id}] 🔄 A procurar alternativa (exceto {failed_ip})...")
                            
                            # AQUI: Usamos o exclude_ip
                            best_neigh = self.find_best_active_neighbour(video, exclude_ip=failed_ip)
                            
                            if best_neigh:
                                print(f"[{self.node_id}] ✅ Alternativa encontrada: {best_neigh}. A enviar START.")
                                start_msg = Message.create_stream_start_message(
                                    srcip=self.node_ip, destip=best_neigh, video=video
                                )
                                self.send_tcp_message(best_neigh, start_msg)
                            else:
                                print(f"[{self.node_id}] ❌ Nenhuma outra rota disponível.")
    
    def activate_route(self, video, neighbor_ip):
        """Marca a rota como ativa **apenas se o vizinho estiver ativo**."""

        # Se o vizinho estiver inativo → NÃO ativa rota
        if not self.neighbors.get(neighbor_ip, False):
            return

        if video in self.routing_table:
            with self.lock:
                for route in self.routing_table[video]:
                    if route["next_hop"] == neighbor_ip:
                        if not route["is_active"]:
                            route["is_active"] = True
                            print(f"[{self.node_id}] Rota ATIVADA para {video} via {neighbor_ip} (RTP recebido)")

    def handle_teardown(self, msg):
        sender_ip = msg.get_src()
        payload = msg.get_payload()
        video = payload.get("video")

        print(f"[{self.node_id}] Recebido TEARDOWN de {sender_ip} para {video}")
        if self.is_server:
            self.server.stop_stream_to_client(sender_ip)
        
        # Remove client from distribution list
        if video in self.downstream_clients:
            if sender_ip in self.downstream_clients[video]:
                self.downstream_clients[video].remove(sender_ip)
                print(f"[{self.node_id}] Cliente {sender_ip} removido da lista de {video}.")

            # Check if theres another client
            if len(self.downstream_clients[video]) == 0:
                print(f"[{self.node_id}] Último cliente saiu. A fechar a rota para {video}...")
                
                if video in self.routing_table:
                    best_route = None
                    for route in self.routing_table[video]:
                        if route["is_active"]:
                            # Marcamos como INATIVO
                            route["is_active"] = False
                            best_route = route["next_hop"]
                            
                            if best_route:
                                print(f"[{self.node_id}] A enviar TEARDOWN para cima ({best_route}).")
                                forward_msg = Message(
                                    msg_type=MsgType.TEARDOWN,
                                    srcip=self.node_ip,
                                    destip=best_route,
                                    payload={"video": video}
                                )
                                self.send_tcp_message(best_route, forward_msg)
            else:
                print(f"[{self.node_id}] Ainda restam {len(self.downstream_clients[video])} clientes. A rota mantém-se ATIVA.")
        
        return best_route

    def get_next_hop_for_ping(self, previous_hop):
        """Escolhe o vizinho ativo para onde enviar o PING, evitando loop."""
        for neigh, active in self.neighbors.items():
            if active and neigh != previous_hop:
                return neigh
        return None

        # Remove client from distribution list
        if video in self.downstream_clients:
            if sender_ip in self.downstream_clients[video]:
                self.downstream_clients[video].remove(sender_ip)
                print(f"[{self.node_id}] Cliente {sender_ip} removido da lista de {video}.")

            # Check if theres another client
            if len(self.downstream_clients[video]) == 0:
                print(f"[{self.node_id}] Último cliente saiu. A fechar a rota para {video}...")
                
                if video in self.routing_table:
                    best_route = None
                    for route in self.routing_table[video]:
                        if route["is_active"]:
                            # Marcamos como INATIVO
                            route["is_active"] = False
                            best_route = route["next_hop"]
                            
                            if best_route:
                                print(f"[{self.node_id}] A enviar TEARDOWN para cima ({best_route}).")
                                forward_msg = Message(
                                    msg_type=MsgType.TEARDOWN,
                                    srcip=self.node_ip,
                                    destip=best_route,
                                    payload={"video": video}
                                )
                                self.send_tcp_message(best_route, forward_msg)
            else:
                print(f"[{self.node_id}] Ainda restam {len(self.downstream_clients[video])} clientes. A rota mantém-se ATIVA.")


# ------------------------------------------------------------------
# MAIN (Ponto de Entrada)
# ------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 4: 
        print("Uso: python3 node.py NODE_ID NODE_IP BOOTSTRAPPER_IP [--server] VIDEO  ")
        print("\nExemplo Servidor:")
        print("  python3 node.py streamer 10.0.0.20 10.0.20.20 --server video1.Mjpeg")
        sys.exit(1)

    node_id = sys.argv[1]
    node_ip = sys.argv[2]
    boot_ip = sys.argv[3]
    video = sys.argv[5] if len(sys.argv) > 5 else None

    
    is_server_flag = "--server" in sys.argv    
    
    
    node = Node(node_id, node_ip, boot_ip, is_server=is_server_flag, video=video)

    # 2. Iniciar serviços (Etapa 1: Registar e Escutar)
    node.start()

    time.sleep(2)

    # 3. Loop de comandos interativos
    if node.is_server:
        prompt_text = f"[{node.node_id}] (Servidor) Comando (flood / routes / neigh / exit): \n"
    else:
        prompt_text = f"[{node.node_id}] (Nó)  Comando (routes / neigh / leave / exit): \n "

    while True:
        try:
            cmd = input(prompt_text).strip().lower()
            
            if cmd == "flood":
                if node.is_server:
                    node.start_flood()
                else:
                    print("Erro: Apenas o servidor pode iniciar um 'flood'.")
                    
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