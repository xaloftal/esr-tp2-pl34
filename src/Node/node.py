# Ficheiro: src/Node/node.py
import sys
import os
import threading
import time
import uuid
from enum import Enum

# Importa as nossas lógicas de "cliente" e "servidor"
from control_client import register_with_bootstrapper, send_tcp_message
from control_server import ControlServer
# Importa a porta TCP partilhada
from config import NODE_TCP_PORT


class MessageType(Enum):
    """Tipos de mensagens de controlo (TCP)"""
    FLOOD = "FLOOD"          # Para Etapa 2 (Construção de Rotas)
    ALIVE = "ALIVE"          # Para Etapa 1 (Manutenção)
    LEAVE = "LEAVE"          # Nó a sair da rede


class Node:
    """
    O "cérebro" do nó. Mantém o estado (vizinhos, rotas) e
    define a lógica de processamento de mensagens.
    """
    
    def __init__(self, node_id, node_ip, is_server=False):
        self.node_id = node_id
        self.node_ip = node_ip
        self.last_alive = {}     # dicionário: {ip : timestamp}
        self.fail_count = {}     # dicionário: {ip : nº de falhas}
        self.leave_cache = set()
        self.flood_cache = set()
        self.network_ready = False

        # --- Flag de Servidor ---
        self.is_server = is_server 
        print(f"[{self.node_id}] Tipo: {'Servidor de Stream' if self.is_server else 'Cliente/Nó Intermédio'}")
        
        # --- Estado da Etapa 1: Topologia Overlay ---
        self.neighbors = [] # Lista de IPs vizinhos
        # O "servidor" P2P que escuta por mensagens
        self.server = ControlServer(self.node_ip, self.handle_incoming_message)
        
        
        # --- Estado da Etapa 2: Rotas ---
        # {destination_ip: (next_hop_ip, metrica)}
        self.routing_table = {} 
        self.flood_cache = set() # Evita loops de flood
        
        self.lock = threading.Lock() 

    def start(self):
        """Inicia todos os serviços do nó."""
        
        # ETAPA 1: Registar e obter vizinhos
        print(f"[{self.node_id}] A registar-se no bootstrapper...")
        self.neighbors = register_with_bootstrapper(self.node_ip)
        
        if not self.neighbors and not self.is_server:
             print(f"[{self.node_id}] Aviso: Não foram obtidos vizinhos.")

        # ETAPA 1: Iniciar o "servidor" para escutar vizinhos
        self.server.start()
        t = threading.Thread(target=self.maintenance_loop, daemon=True)
        t.start()
        
        print(f"[{self.node_id}] Nó iniciado. Vizinhos: {self.neighbors}")

    def handle_incoming_message(self, msg, sender_ip):
        """Processa mensagens recebidas do TCP."""
        if not self.network_ready:
            self.network_ready = True

        msg_type = msg.get("msg_type", "")

        # --- FLOOD ---
        if msg_type == MessageType.FLOOD.value:
            self.handle_flood_message(msg, sender_ip)

        # --- ALIVE recebido: responder silenciosamente ---
        elif msg_type == MessageType.ALIVE.value:
            reply = {
                "msg_type": "ESTOU_AQUI",
                "src": self.node_ip
            }
            send_tcp_message(sender_ip, reply)
            

        # --- ESTOU_AQUI recebido: atualizar estado do vizinho ---
        elif msg_type == "ESTOU_AQUI":
            print(f"[{self.node_id}] {sender_ip} está vivo")

        # --- LEAVE ---
        elif msg_type == MessageType.LEAVE.value:
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
                send_tcp_message(neigh, new_msg)


    
    def announce_leave(self):
        msg = {
            "msg_type": MessageType.LEAVE.value,
            "node_ip": self.node_ip
        }

        print(f"[{self.node_id}] A anunciar LEAVE...")

        for neigh_ip in self.neighbors:
            send_tcp_message(neigh_ip, msg)

        # garantir que a mensagem sai antes do processo morrer
        time.sleep(0.2)


    def handle_leave_message(self, msg, sender_ip):
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
        Remove um vizinho morto sem tratar como LEAVE recebido.
        (Não mostra mensagem LEAVE e não propaga nada.)
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


    def maintenance_loop(self):
        while not self.network_ready:
            time.sleep(1)

        HEARTBEAT_INTERVAL = 5      # de quanto em quanto tempo enviamos ALIVE
        FAIL_TIMEOUT = 15           # se 15 segundos sem ESTOU_AQUI → suspeito
        MAX_FAILS = 3              # falha repetida 3 vezes → morto

        while True:
            time.sleep(HEARTBEAT_INTERVAL)
            now = time.time()

            for neigh in list(self.neighbors):

                # enviar ALIVE silencioso
                send_tcp_message(neigh, { "msg_type": "ALIVE", "src": self.node_ip })

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


                    

    def start_flood(self):
        """Inicia um FLOOD para se dar a conhecer (Etapa 2)."""
        flood_id = str(uuid.uuid4())
        msg = {
            "msg_type": MessageType.FLOOD.value,
            "msg_id": flood_id,
            "srcip": self.node_ip, # Eu sou a origem
            "data": {"hop_count": 0}, # Métrica inicial
            # latencia
        }

        print(f"[{self.node_id}] A iniciar FLOOD (Etapa 2) id={flood_id}...")
        
        with self.lock:
            self.flood_cache.add((self.node_ip, flood_id))

        # Enviar para todos os vizinhos diretos
        for neigh_ip in self.neighbors:
            send_tcp_message(neigh_ip, msg)

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

    
    is_server_flag = "--server" in sys.argv
    
    node = Node(node_id, node_ip, is_server=is_server_flag)

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