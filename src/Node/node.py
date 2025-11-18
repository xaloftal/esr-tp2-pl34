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


class Node:
    """
    O "cérebro" do nó. Mantém o estado (vizinhos, rotas) e
    define a lógica de processamento de mensagens.
    """
    
    def __init__(self, node_id, node_ip, is_server=False):
        self.node_id = node_id
        self.node_ip = node_ip
        
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
        
        print(f"[{self.node_id}] Nó iniciado. Vizinhos: {self.neighbors}")

    def handle_incoming_message(self, msg, sender_ip):
        """
        Callback. O 'ControlServer' chama esta função quando
        recebe uma mensagem completa.
        """
        msg_type = msg.get("msg_type")
        
        # (Substituímos 'match/case' por 'if/elif' para compatibilidade)
        if msg_type == MessageType.FLOOD.value:
            # ETAPA 2: Processar mensagem de construção de rota
            self.handle_flood_message(msg, sender_ip)
            
        elif msg_type == MessageType.ALIVE.value:
            # ETAPA 1: Processar mensagem de manutenção
            print(f"[{self.node_id}] Recebido ALIVE de {sender_ip}")
        
        else:
            print(f"[{self.node_id}] Mensagem desconhecida de {sender_ip}: {msg_type}")

    # ------------------------------------------------------------------
    # ETAPA 2: LÓGICA DE CONSTRUÇÃO DE ROTAS (Flooding)
    # ------------------------------------------------------------------
    
    def handle_flood_message(self, msg, sender_ip):
        """
        Lógica de inundação para 'Estratégia 1'.
        """
        src_ip = msg.get("srcip") 
        msg_id = msg.get("msg_id")
        data = msg.get("data", {})
        hop_count = data.get("hop_count", 0) # Métrica
        
        key = (src_ip, msg_id)

        with self.lock:
            # 1. Evitar loops/repetições
            if key in self.flood_cache:
                return
            
            # 2. Guardar na cache
            self.flood_cache.add(key)
            
            # 3. Atualizar Tabela de Rotas
            if src_ip and src_ip != self.node_ip:
                current_route_hop = self.routing_table.get(src_ip, (None, float('inf')))[1]
                
                if hop_count < current_route_hop:
                    # Armazena (next_hop, metrica)
                    self.routing_table[src_ip] = (sender_ip, hop_count)
                    print(f"[{self.node_id}] Nova Rota (Etapa 2): {src_ip} -> via {sender_ip} (Métrica: {hop_count})")

        # 4. Atualizar métrica antes de reenviar
        msg["data"]["hop_count"] = hop_count + 1
        print(msg)
        # 5. Reenviar (inundar) para outros vizinhos
        for neighbor_ip in self.neighbors:
            # Não enviar de volta para quem nos enviou
            if neighbor_ip == sender_ip:
                continue
                
            send_tcp_message(neighbor_ip, msg)

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
        prompt_text = f"[{node.node_id}] (Cliente)  Comando (routes / neigh / exit): "

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
            
            elif cmd == "":
                pass

            else:
                if node.is_server:
                    print("Comandos: flood | routes | neigh | exit")
                else:
                    print("Comandos: routes | neigh | exit")
        
        except KeyboardInterrupt:
            print(f"\n[{node.node_id}] A sair...")
            break