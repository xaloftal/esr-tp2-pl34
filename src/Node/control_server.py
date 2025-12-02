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

    def start(self):
        threading.Thread(target=self._run_server, daemon=True).start()

    def _run_server(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
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

    # SERVIDOR RTP – enviar vídeo para cliente
    def start_stream_to_client(self, client_ip, video_name):
        print(f"[Servidor] Preparar envio RTP de {video_name} para {client_ip}")

        # Se self.video for string → é o path
        # Se for dict → é self.video[video_name]
        if isinstance(self.video, dict):
            video_path = self.video.get(video_name, None)
        else:
            video_path = self.video

        if not video_path:
            print("[Servidor] Erro: vídeo não encontrado na configuração.")
            return

        rtp = RtpServer(video_file=video_path,
                        client_ip=client_ip,
                        client_port=self.UDPport)
        rtp.start()

        print(f"[Servidor] Envio de {video_name} iniciado para {client_ip}")
