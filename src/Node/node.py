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
# Importa a porta TCP partilhada
from config import NODE_TCP_PORT, BOOTSTRAPPER_PORT, NODE_UDP_PORT
# Import Message class
from aux_files.aux_message import Message, MsgType


class Node:
    """
    O "cérebro" do nó. Mantém o estado (vizinhos, rotas) e
    define a lógica de processamento de mensagens.
    """
    
    def __init__(self, node_id, node_ip, bootstrapper_ip,  is_server=False, video=None, is_client=False):
        
        self.node_id = node_id
        self.node_ip = node_ip
        self.last_alive = {}     # dicionário: {ip : timestamp}
        self.fail_count = {}     # dicionário: {ip : nº de falhas}
        self.leave_cache = set()
        self.join_cache = set()
        self.flood_cache = set()
        self.network_ready = False
        self.bootstrapper_ip = bootstrapper_ip
 
        # --- Flag de Servidor ---
        self.is_server = is_server        
        self.is_client = is_client
        
        
        print(f"[{self.node_id}] Tipo: {'Servidor de Stream' if self.is_server else 'Cliente' if self.is_client else 'Nó Intermédio'}")
        
        # --- Estado da Etapa 1: Topologia Overlay ---
        self.neighbors = {}  # {ip: is_active}
        neighbor_list = self.register_with_bootstrapper(self.node_ip)
        
        for neigh in neighbor_list:
            self.neighbors[neigh] = False  # All neighbors start inactive
        
        if self.is_server:
            self.server = ControlServer(host_ip = self.node_ip,  
                                                    handler_callback = self.handle_incoming_message,   
                                                    video=video)
        else:
            self.server = ControlServer(host_ip = self.node_ip,  
                                                    handler_callback = self.handle_incoming_message)
        
        if self.is_client:
            self.client = ControlClient( node_id = self.node_id, 
                                                        node_ip = self.node_ip, 
                                                        handler_callback = self.handle_incoming_message, video=video)
        
        
        # --- Estado da Etapa 2: Rotas ---
        # {video: {src_ip: [( hop_count, is_active), ...]}}
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
        
        
        
        
    def register_with_bootstrapper(self, node_ip):
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
            return neighbors
        
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
                if video not in self.routing_table:
                    self.routing_table[video] = {}

                if src_ip not in self.routing_table[video]:
                    self.routing_table[video][src_ip] = []

                self.routing_table[video][src_ip].append((hop_count,current_latency ,False))
                print(f"[{self.node_id}] Nova rota para stream {video}: via {src_ip} (hops={hop_count})")

        # ------------------ 6. Criar mensagem atualizada ------------------
        new_msg = Message.create_flood_message(srcip=self.node_ip,origin_flood=origin_ip,flood_id=msg_id,hop_count=hop_count + 1,video=video,start_timestamp=start_ts
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

            # Marcar todas as rotas para este destino como inativas
            for video in self.routing_table:
                if dead_ip in self.routing_table[video]:
                    routes = self.routing_table[video][dead_ip]
                    for i, (metric, is_active) in enumerate(routes):
                        if is_active:
                            self.routing_table[video][dead_ip][i] = (metric, False)

        # NÃO PROPAGAR LEAVE aos outros vizinhos

    def handle_join_message(self, msg):
        """
        processa mensagem JOIN recebida
        """
        new_ip = msg.get_src() if isinstance(msg, Message) else msg.get("srcip")

        # evitar duplicados
        if new_ip in self.join_cache:
            return
        self.join_cache.add(new_ip)        
        # se tiver no leave_cache, remover
        self.leave_cache.discard(new_ip)

        print(f"[{self.node_id}] O vizinho {new_ip} juntou-se à rede.")

        with self.lock:
            # Adicionar ou reativar vizinho
            if new_ip in self.neighbors:
                self.neighbors[new_ip] = True
                print(f"[{self.node_id}] Vizinho {new_ip} reativado")
            else:
                self.neighbors[new_ip] = True
                print(f"[{self.node_id}] Novo vizinho {new_ip} adicionado")
            
            # ativar, se tiver, rotas inativas para este nó
            for video in self.routing_table:
                if new_ip in self.routing_table[video]:
                    routes = self.routing_table[video][new_ip]
                    for i, (metric, is_active) in enumerate(routes):
                        if not is_active:
                            self.routing_table[video][new_ip][i] = (metric, True)

        # NÃO PROPAGAR JOIN aos outros vizinhos
        
        
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
            # sends the message to the best neighbor according to the routing table
            if msg_video not in self.routing_table:
                print(f"[{self.node_id}] Nenhuma rota conhecida para o vídeo {video}.")
                return
            # get the best neighbor (lowest hop count and active)
            
            #TODO: first see if this node already has an active route for that stream, meaning it has the stream passing
            # TODO: add a connected_neighbours list to then send the stream to all the neighbours that are subscribed
            # OR: scan the routing table for the stream and send the packets to all routes that are active
            
            # IF no active route:
            
            best_neigh = self.find_best_neighbour(msg_video)
                
            if best_neigh:
                print(f"[{self.node_id}] A reenviar pedido de stream START para {best_neigh} para vídeo {msg_video}.")
                forward_msg = Message.create_stream_start_message(self.node_ip, msg_video)
                self.send_tcp_message(best_neigh, forward_msg)
            else:
                print(f"[{self.node_id}] Nenhum vizinho encontrado para reenviar pedido de stream START para vídeo {msg_video}.")
                    
               
     # a minha ideia é passar esta para o cliente, já que é uma função só, mas era preciso alguma marosca para mandar aquele find_best_neighbour junto     
    def stream_start_handler(self, video):
            """
            Envia pedido de stream START para o servidor através da melhor rota.
            """
            if video not in self.routing_table:
                print(f"[{self.node_id}] Nenhuma rota conhecida para o vídeo {video}.")
                return

            # Encontrar o melhor vizinho (menor métrica)
            best_neigh = self.find_best_neighbour(video)

            if best_neigh:
                print(f"[{self.node_id}] A pedir stream START ao vizinho {best_neigh} para o vídeo {video}.")
                start_msg = Message.create_stream_start_message(self.node_ip, video)
                self.client.send_tcp_message(best_neigh, start_msg)
            else:
                print(f"[{self.node_id}] Nenhum vizinho ativo encontrado para o vídeo {video}.")
            
            
        

    def local_leave_cleanup(self, dead_ip):
        """
        Remove um vizinho morto - marca rotas como inativas
        """
        with self.lock:
            # Marcar vizinho como inativo
            if dead_ip in self.neighbors:
                self.neighbors[dead_ip] = False
                print(f"[{self.node_id}] Vizinho {dead_ip} marcado como inativo (timeout)")
            
           # Marcar todas as rotas para este destino como inativas
            for video in self.routing_table:
                if dead_ip in self.routing_table[video]:
                    routes = self.routing_table[video][dead_ip]
                    for i, (metric, is_active) in enumerate(routes):
                        if is_active:
                            # Marcar como inativa em vez de remover
                            self.routing_table[video][dead_ip][i] = (metric, False)
                            print(f"[{self.node_id}] Rota inativada: stream {video}, destino {dead_ip}")



    
    def heartbeat(self):
        while not self.network_ready:
            time.sleep(1)

        HEARTBEAT_INTERVAL = 5      # de quanto em quanto tempo enviamos ALIVE
        FAIL_TIMEOUT = 10           # se 10 segundos sem ESTOU_AQUI → suspeito
        MAX_FAILS = 3              # falha repetida 3 vezes → morto

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


                    
    def find_best_neighbour(self, video):
        """aux function to retrieve the best neighbour"""
        best_neigh = None
        best_metric = float('inf')
                
        for neigh_ip, routes in self.routing_table[video].items():
            for metric in routes:
                if metric < best_metric:
                    best_metric = metric
                    best_neigh = neigh_ip
                    
        return best_neigh


# ------------------------------------------------------------------
# MAIN (Ponto de Entrada)
# ------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 4: 
        print("Uso: python3 node.py NODE_ID NODE_IP BOOTSTRAPPER_IP [--server || --client] VIDEO  ")
        print("\nExemplo Servidor:")
        print("  python3 node.py streamer 10.0.0.20 10.0.20.20 --server video1.Mjpeg")
        print("\nExemplo Cliente:")
        print("  python3 node.py c2 10.0.0.21 10.0.20.20 --client video1.Mjpeg")
        sys.exit(1)

    node_id = sys.argv[1]
    node_ip = sys.argv[2]
    boot_ip = sys.argv[3]
    video = sys.argv[5] if len(sys.argv) > 5 else None

    
    is_server_flag = "--server" in sys.argv    
    is_client_flag = "--client" in sys.argv
    
    if is_server_flag and is_client_flag:
        print("Erro: Um nó não pode ser simultaneamente servidor e cliente.")
        sys.exit(1)
    
    node = Node(node_id, node_ip, boot_ip, is_server=is_server_flag, is_client=is_client_flag, video=video)

    # 2. Iniciar serviços (Etapa 1: Registar e Escutar)
    node.start()

    time.sleep(2)

    # 3. Loop de comandos interativos
    if node.is_server:
        prompt_text = f"[{node.node_id}] (Servidor) Comando (flood / routes / neigh / exit): "
    elif node.is_client:
        prompt_text = f"[{node.node_id}] (Cliente)  Comando (routes / neigh / start_video / leave / exit): "
    else:
        prompt_text = f"[{node.node_id}] (Nó)  Comando (routes / neigh / leave / exit): "

    while True:
        try:
            cmd = input(prompt_text).strip().lower()
            
            if cmd == "flood":
                if node.is_server:
                    node.server.start_flood()
                else:
                    print("Erro: Apenas o servidor pode iniciar um 'flood'.")
                    
            elif cmd == "routes":
                print(f"[{node.node_id}] Tabela de Rotas (video: [source_ip: ( Métrica, Latência,is_active))]:")
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
            
            elif cmd == "start_video":
                # if is client and the route table is not empty
                if node.is_client and node.routing_table:
                    node.stream_start_handler(video=node.client.video)
            
            elif cmd == "":
                print(prompt_text)
                
        
        except KeyboardInterrupt:
            print(f"\n[{node.node_id}] A sair...")
            break