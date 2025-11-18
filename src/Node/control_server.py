# Ficheiro: src/Node/control_server.py
import socket
import threading
import json
from config import NODE_TCP_PORT

def parse_message(raw):
    """Converte bytes/string JSON -> dict Python."""
    if isinstance(raw, bytes):
        raw = raw.decode(errors="ignore")
    try:
        return json.loads(raw)
    except Exception:
        return None

class ControlServer:
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
        self.port = NODE_TCP_PORT
        self.handler_callback = handler_callback
        self.server_socket = None
        print(f"[Servidor] A preparar listener em {self.host_ip}:{self.port}")

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

            msg = parse_message(raw_data)
            if not msg:
                print(f"[Servidor] Mensagem JSON inválida de {sender_ip}")
                return
            
            # Entrega a mensagem ao "cérebro" (node.py)
            self.handler_callback(msg, sender_ip)

        except Exception as e:
            print(f"[Servidor] Erro a ler dados de {sender_ip}: {e}")
        finally:
            conn.close()