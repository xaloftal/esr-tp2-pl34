import socket
import threading
import json
from config import NODE_TCP_PORT, NODE_UDP_PORT
from aux_files.aux_message import Message, MsgType, create_flood_message

class ControlServer():
    """
    Lado "servidor" do nó P2P: escuta por conexões TCP de controlo.
    """
    
    def __init__(self, host_ip, handler_callback):
        """
        :param host_ip: O IP local onde este nó deve escutar.
        :param handler_callback: A função (no 'node.py') a chamar 
                                 quando uma mensagem chega.
        """
        self.host_ip = host_ip
        self.TCPport = NODE_TCP_PORT
        self.UDPport = NODE_UDP_PORT
        self.handler_callback = handler_callback
        self.server_socket = None
        
        

    def start(self):
        """Inicia o listener do servidor numa thread separada."""
        threading.Thread(target=self._run_server, daemon=True).start()

    def _run_server(self):
        """Loop principal do servidor (corre na thread)."""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host_ip, self.port))
            self.server_socket.listen()
            print(f"[Servidor] A escutar em {self.host_ip}:{self.port}")

            while True:
                conn, addr = self.server_socket.accept()
                threading.Thread(target=self._handle_connection, args=(conn, addr), daemon=True).start()
        
        except Exception as e:
            print(f"[Servidor] Erro fatal no servidor: {e}")
            if self.server_socket:
                self.server_socket.close()
                

    def _handle_connection(self, conn, addr):
        """Lida com uma única conexão TCP de um vizinho."""
        sender_ip = addr[0]
        try:
            raw_data = conn.recv(65535) # Recebe a mensagem completa
            if not raw_data:
                return

            # Parse using Message class
            msg = Message.from_bytes(raw_data)
            if not msg:
                print(f"[Servidor] Mensagem JSON inválida de {sender_ip}")
                return
            
            # Entrega a mensagem ao "cérebro" (node.py)
            self.handler_callback(msg, sender_ip)

        except Exception as e:
            print(f"[Servidor] Erro a ler dados de {sender_ip}: {e}")
        finally:
            conn.close()
            
            
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