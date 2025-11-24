# Ficheiro: src/Node/control_client.py
import socket
from aux_files.aux_message import Message, MsgType
from config import NODE_TCP_PORT, NODE_UDP_PORT


class ControlClient():
    """Classe para o cliente, herda da Node"""       
    
    def __init__(self, node_id, node_ip, handler_callback, video):
        self.node_id = node_id
        self.node_ip = node_ip
        self.handler_callback = handler_callback
        self.TCPport = NODE_TCP_PORT
        self.UDPport = NODE_UDP_PORT
        
        # video que quer ver
        self.video = video
        
    def start(self):
        # have the listener start, on the handler callback
        threading.Thread(target=self._run_client, daemon=True).start()
        
        
    def _run_client(self):
        try:
            # for tcp, use the handler callback to process messages
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.bind((self.node_ip, self.TCPport))
            self.client_socket.listen()
            print(f"[Cliente] A escutar em {self.node_ip}:{self.TCPport}")
            
            while True:
                conn, addr = self.client_socket.accept()
                threading.Thread(target=self._handle_connection, args=(conn, addr), daemon=True).start()
        
        except Exception as e:
            print(f"[Cliente] Erro fatal no cliente: {e}")
            if self.client_socket:
                self.client_socket.close()
                
                
                
    def _handle_connection(self, conn, addr):
        try:
            data = conn.recv(4096)
            if not data:
                return
            
            msg = Message.from_bytes(data)
            self.handler_callback(msg)
        
        except Exception as e:
            print(f"[Cliente] Erro ao lidar com a conexão de {addr}: {e}")
        finally:
            conn.close()
            
    # TODO: have this one be the one that asks for the video, knowing the best neighbour     
    def ask_start_stream(self, video, neigh):
        pass
        

        
    

   
