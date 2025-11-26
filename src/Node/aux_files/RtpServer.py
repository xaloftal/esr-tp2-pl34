import socket
import threading
import time
from aux_files.RtpPacket import RtpPacket

class RtpServer(threading.Thread):

    def __init__(self, video_file, client_ip, client_port):
        super().__init__(daemon=True)
        self.video_file = video_file
        self.client_ip = client_ip
        self.client_port = client_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.running = True
        self.seqnum = 0

    def run(self):
        print(f"[RTP] A enviar {self.video_file} para {self.client_ip}:{self.client_port}")

        try:
            f = open(self.video_file, "rb")
        except FileNotFoundError:
            print("[RTP] Erro: vídeo não encontrado.")
            return

        while self.running:
            data = f.read(1024)
            if not data:
                break

            packet = RtpPacket()
            packet.encode(
                version=2, padding=0, extension=0, cc=0,
                seqnum=self.seqnum, marker=0, pt=26,
                ssrc=0, payload=data
            )

            self.sock.sendto(packet.getPacket(), (self.client_ip, self.client_port))
            self.seqnum += 1
            time.sleep(0.04)  # ~25 fps

        f.close()
        print("[RTP] Fim do stream.")

    def stop(self):
        self.running = False
