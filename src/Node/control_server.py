# control_server.py
import socket
import threading
from config import NODE_TCP_PORT, NODE_RTP_PORT
from aux_files.aux_message import Message
from aux_files.RtpServer import RtpServer   

class ControlServer:
    def __init__(self, host_ip, handler_callback, video=None):
        self.host_ip = host_ip
        self.TCPport = NODE_TCP_PORT
        self.UDPport = NODE_RTP_PORT
        self.handler_callback = handler_callback
        self.video = video      # pode ser string ou dict
        self.server_socket = None
        self.active_streams = {}

    def start(self):
        threading.Thread(target=self._run_server, daemon=True).start()

    def _run_server(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(("0.0.0.0", self.TCPport))
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
        try:
            raw = conn.recv(65535)
            if not raw:
                return

            msg = Message.from_bytes(raw)
            if msg:
                self.handler_callback(msg)
        except Exception as e:
            print(f"[Servidor] Erro a ler dados de {addr[0]}: {e}")
        finally:
            conn.close()

    def start_stream_to_client(self, client_ip, video_name):
        print(f"[Servidor] Preparar envio RTP de {video_name} para {client_ip}")


        if isinstance(self.video, dict):
            video_path = self.video.get(video_name, None)
        else:
            video_path = self.video

        if not video_path:
            print("[Servidor] Erro: vídeo não encontrado na configuração.")
            return
        if client_ip in self.active_streams:
            print(f"[Servidor] Já existe stream para {client_ip}. A reiniciar...")
            self.active_streams[client_ip].stop()
            del self.active_streams[client_ip]
    
        # CRITICAL: Pass video_name for SSRC, not video_path
        rtp = RtpServer(video_file=video_path,
                        video_name=video_name,
                        client_ip=client_ip,
                        client_port=self.UDPport)
        rtp.start()
        self.active_streams[client_ip] = rtp

    def stop_stream_to_client(self, client_ip):
        """Pára o envio de stream para um cliente específico."""
        if client_ip in self.active_streams:
            print(f"[Servidor] A parar stream para {client_ip}...")
            
            self.active_streams[client_ip].stop()
            
            # Remove da lista de ativos
            del self.active_streams[client_ip]
        else:
            print(f"[Servidor] Pedido de paragem para {client_ip}, mas não há stream ativo.")
    

        
