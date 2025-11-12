# control_server.py
import socket
import json
import threading
import uuid
import time
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Node.node import Node
from Proto.aux_message import MessageType, create_message


class Server(Node):
    def __init__(self, node_id, node_ip, bootstrapper_ip,
                 bootstrapper_port=1000, tcpport=6000, udpport=7000,
                 videosrc=None):
        super().__init__(node_id, node_ip, bootstrapper_ip, bootstrapper_port,
                         tcpport, udpport)
        self.videosrc = videosrc  # caminho/identificador da fonte de vídeo

    # -------------------------------------------------------------
    # FLOOD
    # -------------------------------------------------------------
    def initiate_flood(self):
        """Inicia um FLOOD para construir routing tables na rede."""
        flood_id = str(uuid.uuid4())
        print(f"[{self.node_id}] Initiating flood with ID: {flood_id}")

        for neighbor_ip in self.neighbors:
            msg = create_message(
                msg_id=flood_id,
                msg_type=MessageType.FLOOD,
                srcip=self.node_ip,
                destip=neighbor_ip,
                data={
                    "hop_count": 0
                }
            )
            self.send_tcp_message(neighbor_ip, msg)

        with self.lock:
            self.flood_cache.add(flood_id)

        print(f"[{self.node_id}] Flood initiated and sent to neighbors")

    def manual_flood(self):
        """Trigger manual de flood, por exemplo a partir da linha de comandos."""
        print(f"\n[{self.node_id}] === Manual Flood Triggered ===")
        self.initiate_flood()

    # -------------------------------------------------------------
    # STREAMING (esqueleto)
    # -------------------------------------------------------------
    def start_stream_to(self, dest_ip, stream_id="default"):
        """
        Exemplo: envia mensagem STREAM_START para dest_ip.
        Depois, poderias iniciar envio de dados via UDP.
        """
        msg = create_message(
            msg_id=str(uuid.uuid4()),
            msg_type=MessageType.STREAM_START,
            srcip=self.node_ip,
            destip=dest_ip,
            data={"stream_id": stream_id}
        )
        self.send_tcp_message(dest_ip, msg)
        print(f"[{self.node_id}] STREAM_START sent to {dest_ip} for stream {stream_id}")
        # Aqui poderias iniciar uma thread que lê frames de self.videosrc
        # e envia via UDP com MessageType.STREAM_DATA
