import socket
import threading
import json
from config import NODE_TCP_PORT, NODE_UDP_PORT
from aux_files.aux_message import Message, MsgType

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
    
    def __init__(self, host_ip, handler_callback, video):
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
        
        #video(s) disponível(is)
        self.video = video
        

    def start(self):
        """Inicia o listener do servidor numa thread separada."""
        threading.Thread(target=self._run_server, daemon=True).start()

    def _run_server(self):
        """Loop principal do servidor (corre na thread)."""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.bind((self.host_ip, self.TCPport))
            self.server_socket.listen()
            print(f"[Servidor] A escutar em {self.host_ip}:{self.TCPport}")

            while True:
                conn, addr = self.server_socket.accept()
                threading.Thread(target=self._handle_connection, args=(conn, addr), daemon=True).start()
        
        except Exception as e:
            print(f"[Servidor] Erro fatal no servidor: {e}")
            if self.server_socket:
                self.server_socket.close()
                

    def _handle_connection(self, conn, addr):
        """Lida com uma única conexão TCP de um vizinho."""
        connection_ip = addr[0]  # IP real da conexão
        try:
            raw_data = conn.recv(65535) # Recebe a mensagem completa
            if not raw_data:
                return

            # Parse using Message class
            msg = Message.from_bytes(raw_data)
            if not msg:
                print(f"[Servidor] Mensagem JSON inválida de {connection_ip}")
                return           
            # Entrega a mensagem ao "cérebro" (node.py)
            self.handler_callback(msg)

        except Exception as e:
            print(f"[Servidor] Erro a ler dados de {sender_ip}: {e}")
        finally:
            conn.close()
            
            
            
    def start_flood(self):
        """
        Inicia um flood pela rede (apenas servidor).
        """
        msg_id = str(uuid.uuid4())
        # Se não fornecer video, usar o IP do nó como identificador
        key = (self.node_ip, msg_id)
        
        with self.lock:
            self.flood_cache.add(key)
        flood_msg = Message.create_flood_message(self.node_ip, origin_flood = self.node_ip, flood_id=msg_id, hop_count=0, video=self.video)
        
        print(f"[{self.node_id}] A iniciar FLOOD com ID {msg_id} para stream {self.video}")
        
        # Enviar para todos os
        for neigh, is_active in self.neighbors.items():
            self.send_tcp_message(neigh, flood_msg)
            
    
    
    
    def start_stream_to_client(self, client_ip, video):
        """Inicia o envio do stream de vídeo para o cliente."""
        # Aqui implementamos o envio do vídeo via RTP/UDP
        # Esta função deve criar um servidor RTP que envia os pacotes para o client_ip
        
        # video is an array of available videos
        rtp_server = RtpServer(
            video_file=self.video[video],  # Assumindo que self.video é um dicionário {video: video_path}
            client_ip=client_ip,
            client_port=self.UDPport
        )
        rtp_server.start()
        print(f"[{self.node_id}] Envio do stream {video} iniciado para {client_ip}.")