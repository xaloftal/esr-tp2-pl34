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
        self.leave_cache = set()
        self.join_cache = set()
        self.flood_cache = set()
        self.network_ready = False
        self.bootstrapper_ip = bootstrapper_ip
        self.video = video
         
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
        # {video: [{"next_hop": ip, "metric": (hop_count, latency_ms), "is_active": bool}, ...]}
        self.routing_table = {} 
        self.flood_cache = set() # Evita loops de flood
        self.lock = threading.Lock() 
        
        
        

    def start(self):
        """Inicia todos os serviços do nó."""   

        # ETAPA 1: Iniciar o "servidor" para escutar vizinhos
        self.server.start()
        t = threading.Thread(target=self.heartbeat, daemon=True)
        t.start()
        
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
            print(f"[{self.node_id}] {msg_sender} está vivo")
        
        elif msg_type == MsgType.LEAVE:
            self.handle_leave_message(msg)
        
        elif msg_type == MsgType.JOIN:
            self.handle_join_message(msg)
            
        elif msg_type == MsgType.STREAM_START:
            self.handle_stream_start(msg)
        
        else:
            print(f"[{self.node_id}] Tipo de mensagem desconhecido: {msg_type}")
            
            

    # ------------------------------------------------------------------
    # ETAPA 2: LÓGICA DE CONSTRUÇÃO DE ROTAS (Flooding)
    # ------------------------------------------------------------------
    def handle_flood_message(self, msg):
        """
            flood
        """
        src_ip = msg.get_src() if isinstance(msg, Message) else msg.get("srcip")
        msg_id = msg.id if isinstance(msg, Message) else msg.get("msg_id")
        payload = msg.get_payload() if isinstance(msg, Message) else msg.get("payload", {})

        hop_count = payload.get("hop_count", 0)
        video = payload.get("video", None)
        start_ts = payload.get("start_timestamp", time.time())
        current_latency = (time.time() - start_ts) * 1000

        # ------------------- 2. Identificação do originador -------------------
        origin_ip = payload.get("origin_ip", src_ip)

        # A chave de flood deve ser baseada no originador (constante), não no vizinho atual
        key = (origin_ip, msg_id)

        with self.lock:
            if key in self.flood_cache:
                return

            # ------------------ 4. Registar flood ------------------
            self.flood_cache.add(key)

            if src_ip and src_ip != self.node_ip and video:
                # Estrutura: {video: [{"next_hop": ip, "metric": (hop, lat), "is_active": bool}, ...]}
                new_route = {
                    "next_hop": src_ip,
                    "metric": (hop_count, current_latency),
                    "is_active": False
                }

                # Se ainda não há rotas para este vídeo → cria lista
                if video not in self.routing_table:
                    self.routing_table[video] = [new_route]
                    print(f"[{self.node_id}] Nova rota para stream {video}: via {src_ip} (hops={hop_count})")

                else:
                    # Verificar se já temos rota por este next_hop
                    existing_route = None
                    for route in self.routing_table[video]:
                        if route["next_hop"] == src_ip:
                            existing_route = route
                            break

                    if existing_route:
                        # Atualizar rota existente se a nova for melhor
                        old_hop, old_lat = existing_route["metric"]
                        new_hop, new_lat = new_route["metric"]
                        
                        if new_hop < old_hop or (new_hop == old_hop and new_lat < old_lat):
                            existing_route["metric"] = (new_hop, new_lat)
                            existing_route["is_active"] = True
                            print(f"[{self.node_id}] Rota MELHORADA para {video}: via {src_ip} (hops={hop_count})")
                        else:
                            # Reativar rota antiga se estava inativa
                            if not existing_route["is_active"]:
                                existing_route["is_active"] = True
                                print(f"[{self.node_id}] Rota reativada para {video}: via {src_ip}")
                    else:
                        # Adicionar nova rota à lista
                        self.routing_table[video].append(new_route)
                        print(f"[{self.node_id}] Nova rota alternativa para {video}: via {src_ip} (hops={hop_count})")
                    

        # ------------------ 6. Criar mensagem atualizada ------------------
        new_msg = Message.create_flood_message(
            srcip=self.node_ip,
            origin_flood=origin_ip,
            flood_id=msg_id,
            hop_count=hop_count + 1,
            video=video,
            start_timestamp=start_ts
        )


        # ------------------ 7. Reenviar para vizinhos ------------------
        for neigh, is_active in self.neighbors.items():
            if neigh != src_ip:
                self.send_tcp_message(neigh, new_msg)

                
    def announce_leave(self):
        """
        Anuncia aos vizinhos que vai sair
        """
        print(f"[{self.node_id}] A anunciar LEAVE...")

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
                        route["is_active"] = True
                        print(f"[{self.node_id}] Rota reativada por JOIN: {video} via {neigh_ip}")


        
    def handle_stream_start(self, msg):
        msg_sender = msg.get_src() if isinstance(msg, Message) else msg.get("srcip")
        msg_payload = msg.get_payload() if isinstance(msg, Message) else msg.get("payload", {})
        msg_video = msg_payload.get("video", None)
        
        if self.is_server:
            # check if it has video on server.video, which is an array
            if msg_video in self.server.video:
                print(f"[{self.node_id}] Pedido de stream {msg_video} recebido de {msg_sender}. A iniciar envio...")
                self.server.start_stream_to_client(msg_sender, msg_video)
            
            else:
                print(f"[{self.node_id}] Pedido de stream {msg_video} recebido de {msg_sender}, mas vídeo não disponível.")
                
        else:
            print(f"[{self.node_id}] Pedido de stream START recebido de {msg_sender} para vídeo {msg_video}, mas não sou servidor.")

            if msg_video not in self.routing_table:
                print(f"[{self.node_id}] Nenhuma rota conhecida para o vídeo {msg_video}.")
                return

            best_neigh = self.find_best_active_neighbour(msg_video)

            if best_neigh:
                print(f"[{self.node_id}] A reenviar pedido de stream START para {best_neigh} para vídeo {msg_video}.")

                forward_msg = Message.create_stream_start_message(
                    srcip=self.node_ip,
                    destip=best_neigh,
                    video=msg_video
                )

                self.send_tcp_message(best_neigh, forward_msg)

            else:
                print(f"[{self.node_id}] Nenhum vizinho encontrado para reenviar pedido de stream START para vídeo {msg_video}.")

               
     # a minha ideia é passar esta para o cliente, já que é uma função só, mas era preciso alguma marosca para mandar aquele find_best_neighbour junto     
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

            # envia através do control client
            #self.client.send_tcp_message(best_neigh, start_msg)
            #é o Node que sabe enviar mensagens TCP, não o cliente.
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

        print(f"[{self.node_id}] A iniciar FLOOD com ID {msg_id} para stream {self.video}")

        # Enviar o flood aos vizinhos
        for neigh_ip in self.neighbors.keys():
            print(f"[{self.node_id}] Enviando FLOOD para {neigh_ip}")
            self.send_tcp_message(neigh_ip, flood_msg)

        

    def local_leave_cleanup(self, dead_ip):
        """
        Remove um vizinho morto - marca rotas como inativas
        """
        with self.lock:
            # Marcar vizinho como inativo
            
             # remove da join_cache se lá estiver
            self.join_cache.discard(dead_ip)
                # adiciona à leave_cache
            self.leave_cache.add(dead_ip)
            if dead_ip in self.neighbors:
                self.neighbors[dead_ip] = False
                print(f"[{self.node_id}] Vizinho {dead_ip} marcado como inativo (timeout)")
            
            # Marcar todas as rotas que usam este next_hop como inativas
            for video, routes in self.routing_table.items():
                for route in routes:
                    if route["next_hop"] == dead_ip:
                        route["is_active"] = False
                        print(f"[{self.node_id}] Rota inativada: stream {video}, via {dead_ip}")



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


                    
    def find_best_active_neighbour(self, video):
        """Escolhe o vizinho ativo com a melhor métrica para um determinado vídeo."""
        if video not in self.routing_table:
            return None
        
        best_route = None
        best_metric = (999999, 999999999)  # (hop_count, latency)
        
        for route in self.routing_table[video]:
            next_hop = route["next_hop"]
            hop_count, latency = route["metric"]
            is_active = route["is_active"]
            
            # Apenas rotas ativas e com vizinho ativo
            if is_active and self.neighbors.get(next_hop, False):
                # Comparar métricas (hop_count primeiro, depois latency)
                if (hop_count < best_metric[0]) or (hop_count == best_metric[0] and latency < best_metric[1]):
                    best_metric = (hop_count, latency)
                    best_route = next_hop
        
        return best_route




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
                print(f"[{node.node_id}] Tabela de Rotas (video: [{{\"next_hop\": ip, \"metric\": (hop_count, latency_ms), \"is_active\": bool}}, ...]):")
                print(node.routing_table)

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