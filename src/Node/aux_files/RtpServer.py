import socket
import threading
import time
import os
import sys
from aux_files.RtpPacket import RtpPacket
from aux_files.VideoStream import VideoStream
from aux_files.video_mapping import video_name_to_ssrc 

class RtpServer(threading.Thread):
    """
    RTP Server (Broadcast Mode): 
    Runs continuously like a TV Station. 
    Maintains a list of subscribers and sends the same frame to all of them simultaneously.
    """

    def __init__(self, video_file, video_name):
        super().__init__(daemon=True)
        self.video_file = video_file
        self.video_name = video_name 
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.running = True
        self.seqnum = 0
        
        # SSRC based on video name
        self.ssrc = video_name_to_ssrc(video_name)
        
        # Absolute path
        self.video_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "videos", self.video_file))
        
        # --- NEW: List of active subscribers (Client IP, Client Port) ---
        self.subscribers = [] 
        self.lock = threading.Lock() # Thread safety for adding/removing clients

    def add_subscriber(self, ip, port):
        """Adds a client to the broadcast list."""
        with self.lock:
            if (ip, port) not in self.subscribers:
                self.subscribers.append((ip, port))
                print(f"[RTP TV] Novo espectador ligado: {ip}:{port}")

    def remove_subscriber(self, ip):
        """Removes a client from the broadcast list."""
        with self.lock:
            # Filter out the client with this IP
            self.subscribers = [s for s in self.subscribers if s[0] != ip]
            print(f"[RTP TV] Espectador saiu: {ip}")

    def run(self):
        """
        Main loop: Reads video frames continuously (Global Time).
        Sends the packet to ALL subscribers in the list.
        """
        print(f"[RTP TV] A iniciar emissão contínua de: {self.video_file}")
        
        try:
            self.video_stream = VideoStream(self.video_path)
        except IOError:
            print(f"[RTP] Erro: vídeo não encontrado em: {self.video_path}")
            return

        while self.running:
            # 1. Get next frame (The 'Time' passes for everyone)
            data = self.video_stream.nextFrame()
            
            # 2. Loop video if finished
            if not data:
                self.video_stream.rewind()
                continue 

            # 3. Create packet (Only once per frame)
            packet = RtpPacket()
            packet.encode(
                version=2, padding=0, extension=0, cc=0,
                seqnum=self.seqnum, marker=0, pt=26,
                ssrc=self.ssrc, payload=data,
                video_name=self.video_name
            )
            packet_bytes = packet.getPacket()

            # 4. Broadcast to all active subscribers
            with self.lock:
                for ip, port in self.subscribers:
                    try:
                        self.sock.sendto(packet_bytes, (ip, port))
                    except:
                        # If sending fails, we could remove the client, but let's keep simple
                        pass

            # 5. Global Sequence Number increases
            self.seqnum += 1
            
            # 6. Global FPS control
            time.sleep(0.04) 

        print("[RTP] Emissão encerrada.")
        self.sock.close()

    def stop(self):
        self.running = False