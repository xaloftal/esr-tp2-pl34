import socket
import threading
import time
import os
import sys
from aux_files.RtpPacket import RtpPacket
# Certifica-te que o import está correto conforme a tua estrutura de pastas
from aux_files.VideoStream import VideoStream 

class RtpServer(threading.Thread):

    def __init__(self, video_file, client_ip, client_port):
        super().__init__(daemon=True)
        self.video_file = video_file
        self.client_ip = client_ip
        self.client_port = client_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.running = True
        self.seqnum = 0
        
        # Calcular o path absoluto
        self.video_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "videos", self.video_file))

    def run(self):
        print(f"[RTP] A enviar {self.video_file} para {self.client_ip}:{self.client_port}")
        
        try:
            self.video_stream = VideoStream(self.video_path)
            
        except IOError:
            print(f"[RTP] Erro: vídeo não encontrado em: {self.video_path}")
            return

        while self.running:
            
            data = self.video_stream.nextFrame()
            
            # Se data vier vazio, chegámos ao fim do vídeo
            if not data:
                # REBOBINAR (Loop Infinito)
                self.video_stream.rewind()
                continue # Volta ao início do while para ler o 1º frame

            # Criar o pacote RTP
            packet = RtpPacket()
            packet.encode(
                version=2, padding=0, extension=0, cc=0,
                seqnum=self.seqnum, marker=0, pt=26,
                ssrc=0, payload=data
            )
            
            self.sock.sendto(packet.getPacket(), (self.client_ip, self.client_port))
            
            # O SeqNum continua a subir, mesmo após o loop, para o cliente não baralhar
            self.seqnum += 1
            
            time.sleep(0.04)  # ~25 fps

        print("[RTP] Fim do stream.")

    def stop(self):
        self.running = False