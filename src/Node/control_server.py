# File: control_server.py
import socket
import threading
from config import NODE_TCP_PORT, NODE_RTP_PORT
from aux_files.aux_message import Message
from aux_files.RtpServer import RtpServer   

class ControlServer:
    """
    Server: Manages TCP connections and manages the 'TV Channels' (RTP Broadcasts).
    """
    
    def __init__(self, host_ip, handler_callback, video=None):
        self.host_ip = host_ip
        self.TCPport = NODE_TCP_PORT
        self.UDPport = NODE_RTP_PORT
        self.handler_callback = handler_callback
        self.video = video # Can be dict or string
        
        self.server_socket = None
        
        # --- NEW: Active Channels Dictionary ---
        # Key: Video Name -> Value: RtpServer Instance (Running Thread)
        self.channels = {} 
        
        # Start the TV Channels immediately!
        self._start_all_channels()

    def _start_all_channels(self):
        """Initializes and starts RtpServer threads for all available videos."""
        videos_to_start = {}
        
        if isinstance(self.video, dict):
            videos_to_start = self.video
            print(f"[Servidor] Configuração Multi-Vídeo: {videos_to_start}")
            
        elif isinstance(self.video, str):
            print(f"[Servidor] Configuração Single-Vídeo: {self.video}")
            videos_to_start = {self.video: self.video}
                    
        for v_name, v_path in videos_to_start.items():
            # Create the broadcaster thread
            rtp = RtpServer(video_file=v_path, video_name=v_name)
            rtp.start()
            self.channels[v_name] = rtp
            print(f"[Servidor] Canal '{v_name}' está NO AR (On Air)!")

    def start(self):
        """Starts the main TCP listener."""
        threading.Thread(target=self._run_server, daemon=True).start()

    def _run_server(self):
        """TCP Loop to accept control connections."""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(("0.0.0.0", self.TCPport))
            self.server_socket.listen()
            print(f"[Servidor] Controlo TCP em {self.host_ip}:{self.TCPport}")

            while True:
                conn, addr = self.server_socket.accept()
                threading.Thread(target=self._handle_connection, args=(conn, addr), daemon=True).start()

        except Exception as e:
            print(f"[Servidor] Erro fatal: {e}")

    def _handle_connection(self, conn, addr):
        """Reads TCP messages."""
        try:
            raw = conn.recv(65535)
            if not raw: return
            msg = Message.from_bytes(raw)
            if msg: self.handler_callback(msg)
        except: pass
        finally: conn.close()

    def start_stream_to_client(self, client_ip, video_name):
        """
        Logic for SETUP/PLAY:
        Instead of creating a new stream, adds the client to the existing channel.
        """
        
        if video_name in self.channels:
            # Add client to the broadcast list
            self.channels[video_name].add_subscriber(client_ip, self.UDPport)
        else:
            print(f"[Servidor] Erro: Canal {video_name} não existe.")

    def stop_stream_to_client(self, client_ip, video_name=None):
        """
        Logic for TEARDOWN:
        Removes the client from the broadcast list. The video keeps running.
        """
        if video_name:
            if video_name in self.channels:
                self.channels[video_name].remove_subscriber(client_ip)
        else:
            # If no video specified, remove from ALL channels (Safety)
            for ch in self.channels.values():
                ch.remove_subscriber(client_ip)