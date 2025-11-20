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
from aux_files.aux_message import Message, MsgType, create_flood_message, create_alive_message, create_leave_message, create_register_message


class Node:
    """
    O "cérebro" do nó. Mantém o estado (vizinhos, rotas) e
    define a lógica de processamento de mensagens.
    """
    
    def __init__(self, node_id, node_ip, bootstrapper_ip,  is_server=False):
        self.node_id = node_id
        self.node_ip = node_ip
        self.last_alive = {}     # dicionário: {ip : timestamp}
        self.fail_count = {}     # dicionário: {ip : nº de falhas}
        self.leave_cache = set()
        self.flood_cache = set()
        self.network_ready = False
        self.bootstrapper_ip = bootstrapper_ip

        # --- Flag de Servidor ---
        self.is_server = is_server 
        print(f"[{self.node_id}] Tipo: {'Servidor de Stream' if self.is_server else 'Cliente/Nó Intermédio'}")
        
        # --- Estado da Etapa 1: Topologia Overlay ---
        self.neighbors = self.register_with_bootstrapper(self.node_ip)
        # O "servidor" P2P que escuta por mensagens
        self.server = ControlServer(self.node_ip, self.handle_incoming_message)
        
        
        # --- Estado da Etapa 2: Rotas ---
        # {destination_ip: (next_hop_ip, metrica)}
        self.routing_table = {} 
        self.flood_cache = set() # Evita loops de flood
        
        self.lock = threading.Lock() 
        
        
        

    def start(self):
        """Inicia todos os serviços do nó."""   

        # ETAPA 1: Iniciar o "servidor" para escutar vizinhos
        self.server.start()
        t = threading.Thread(target=self.maintenance_loop, daemon=True)
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
            message = create_register_message(node_ip, self.bootstrapper_ip)
            client.sendall(message.to_bytes())

            # Recebe a resposta (JSON com a lista de vizinhos)
            response_raw = client.recv(4096).decode()
            client.close()

            data = Message.from_json(response_raw)
            neighbors = data.get_payload().get("neighbours", [])
            
            print(f"[Cliente] Vizinhos recebidos do bootstrapper: {neighbors}")
            return neighbors
        
        except json.JSONDecodeError:
            print(f"[Cliente] Falha a parsear resposta do bootstrapper: {response_raw}")
            return []
        except Exception as e:
            print(f"[Cliente] Erro a ligar/registar no bootstrapper: {e}")
            return []




    def send_tcp_message(self, dest_ip, msg_dict):
        """
        Envia uma mensagem de controlo (dicionário Python) para um nó vizinho.
        """
        try:
            msg = Message.from_dict(msg_dict).to_bytes()
            
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(2.0) # Timeout curto para não bloquear
                
                # Cada nó escuta na mesma porta de controlo
                sock.connect((dest_ip, NODE_TCP_PORT)) 
                sock.sendall(msg)
            return True

        except: #Exception as e:
            # print(f"[Cliente] Erro a enviar TCP para {dest_ip}:{NODE_TCP_PORT}: {e}")
            return #False
        
        

    def handle_incoming_message(self, msg, sender_ip):
        """Processa mensagens recebidas do TCP."""
        if not self.network_ready:
            self.network_ready = True

        msg_type = Message.get_message_type(msg)

        # --- FLOOD ---
        if msg_type == MsgType.FLOOD:
            self.handle_flood_message(msg, sender_ip)

        # --- ALIVE recebido: responder silenciosamente ---
        elif msg_type == MsgType.ALIVE:           
            reply = create_alive_message(self.node_ip, sender_ip)
            self.send_tcp_message(sender_ip, reply)
            
        # --- ESTOU_AQUI recebido: atualizar estado do vizinho ---
        elif msg_type == MsgType.ALIVE_ACK:
            print(f"[{self.node_id}] {sender_ip} está vivo")

        # --- LEAVE ---
        elif msg_type == MsgType.LEAVE:
            self.handle_leave_message(msg, sender_ip)
            
            
            
            

    # ------------------------------------------------------------------
    # ETAPA 2: LÓGICA DE CONSTRUÇÃO DE ROTAS (Flooding)
    # ------------------------------------------------------------------
    
    def handle_flood_message(self, msg, sender_ip):
        """
            flood
        """
        src_ip = msg.get("srcip")
        msg_id = msg.get("msg_id")
        data = msg.get("data", {})
        hop_count = data.get("hop_count", 0)

        key = (src_ip, msg_id)

        with self.lock:
            # 1 — Evitar receber o mesmo FLOOD duas vezes
            if key in self.flood_cache:
                return

            # 2 — Registar FLOOD para não processar de novo
            self.flood_cache.add(key)

            # 3 — Atualizar melhor rota (só se for mais curta)
            if src_ip and src_ip != self.node_ip:
                current = self.routing_table.get(src_ip, (None, float('inf')))[1]

                if hop_count < current:
                    self.routing_table[src_ip] = (sender_ip, hop_count)
                    print(f"[{self.node_id}] Nova rota: {src_ip} -> {sender_ip} (métrica {hop_count})")

        # 4 — Criar cópia segura da mensagem
        new_msg = {
            "msg_type": MessageType.FLOOD.value,
            "msg_id": msg_id,
            "srcip": src_ip,
            "data": {"hop_count": hop_count + 1}
        }

        # 5 — Reenviar FLOOD apenas para outros vizinhos
        for neigh in self.neighbors:
            if neigh != sender_ip:
                self.send_tcp_message(neigh, new_msg)
                
                
                


    
    def announce_leave(self):
        """
        Anuncia aos vizinhos que vai sair
        """
        msg = {
            "msg_type": MessageType.LEAVE.value,
            "node_ip": self.node_ip
        }

        print(f"[{self.node_id}] A anunciar LEAVE...")

        for neigh_ip in self.neighbors:
            self.send_tcp_message(neigh_ip, msg)

        # garantir que a mensagem sai antes do processo morrer
        time.sleep(0.2)


    def handle_leave_message(self, msg, sender_ip):
        """
        processa mensagem LEAVE recebida
        """
        dead_ip = msg.get("node_ip")

        # evitar duplicados
        if dead_ip in self.leave_cache:
            return
        self.leave_cache.add(dead_ip)

        print(f"[{self.node_id}] O vizinho {dead_ip} saiu da rota.")

        with self.lock:
            # remover do conjunto de vizinhos
            if dead_ip in self.neighbors:
                self.neighbors.remove(dead_ip)

            # remover rotas diretas
            if dead_ip in self.routing_table:
                del self.routing_table[dead_ip]

            # remover rotas onde era next hop
            to_delete = []
            for dest, (next_hop, _) in self.routing_table.items():
                if next_hop == dead_ip:
                    to_delete.append(dest)

            for dest in to_delete:
                del self.routing_table[dest]

        # NÃO PROPAGAR LEAVE aos outros vizinhos


    def local_leave_cleanup(self, dead_ip):
        """
        Remove um vizinho morto
        """
        with self.lock:
            if dead_ip in self.neighbors:
                self.neighbors.remove(dead_ip)

            # Remover rotas cujo next hop é o morto
            if dead_ip in self.routing_table:
                del self.routing_table[dead_ip]

            to_delete = []
            for dest, (next_hop, metric) in self.routing_table.items():
                if next_hop == dead_ip:
                    to_delete.append(dest)

            for dest in to_delete:
                del self.routing_table[dest]


    def start_flood(self):
        """
        Inicia um flood pela rede (apenas servidor).
        """
        msg_id = str(uuid.uuid4())
        flood_msg = create_flood_message(self.node_ip, "broadcast", msg_id, hop_count=0)
        
        print(f"[{self.node_id}] A iniciar FLOOD com ID {msg_id}")
        
        # Enviar para todos os vizinhos
        for neigh in self.neighbors:
            self.send_tcp_message(neigh, flood_msg)
    
    def maintenance_loop(self):
        while not self.network_ready:
            time.sleep(1)

        HEARTBEAT_INTERVAL = 5      # de quanto em quanto tempo enviamos ALIVE
        FAIL_TIMEOUT = 10           # se 10 segundos sem ESTOU_AQUI → suspeito
        MAX_FAILS = 3              # falha repetida 3 vezes → morto

        while True:
            time.sleep(HEARTBEAT_INTERVAL)
            now = time.time()

            for neigh in list(self.neighbors):

                # enviar ALIVE silencioso
                self.send_tcp_message(neigh, { "msg_type": "ALIVE", "src": self.node_ip })

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


                    



# ------------------------------------------------------------------
# MAIN (Ponto de Entrada)
# ------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 4: 
        print("Uso: python3 node.py NODE_ID NODE_IP BOOTSTRAPPER_IP [--server]")
        print("\nExemplo Servidor:")
        print("  python3 node.py streamer 10.0.0.20 10.0.20.20 --server")
        print("\nExemplo Cliente:")
        print("  python3 node.py c2 10.0.0.21 10.0.20.20")
        sys.exit(1)

    node_id = sys.argv[1]
    node_ip = sys.argv[2]
    boot_ip = sys.argv[3]

    
    is_server_flag = "--server" in sys.argv
    
    node = Node(node_id, node_ip, boot_ip, is_server=is_server_flag)

    # 2. Iniciar serviços (Etapa 1: Registar e Escutar)
    node.start()

    time.sleep(2)

    # 3. Loop de comandos interativos
    if node.is_server:
        prompt_text = f"[{node.node_id}] (Servidor) Comando (flood / routes / neigh / exit): "
    else:
        prompt_text = f"[{node.node_id}] (Cliente)  Comando (routes / neigh / leave / exit): "

    while True:
        try:
            cmd = input(prompt_text).strip().lower()

            if cmd == "flood":
                if node.is_server:
                    node.start_flood()
                else:
                    print("Erro: Apenas o nó servidor pode iniciar um 'flood'.")

            elif cmd == "routes":
                print(f"[{node.node_id}] Tabela de Rotas (Destino: (Next_Hop, Métrica)):")
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
                pass

            else:
                if node.is_server:
                    print("Comandos: flood | routes | neigh |exit")
                else:
                    print("Comandos: routes | neigh | leave | exit")
        
        except KeyboardInterrupt:
            print(f"\n[{node.node_id}] A sair...")
            break