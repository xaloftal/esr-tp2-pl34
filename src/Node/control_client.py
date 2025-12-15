import json
import socket
import threading
import sys
import time
import os
from tkinter import Tk
from io import BytesIO
from PIL import Image

from aux_files.ClienteGUI import ClienteGUI
from aux_files.RtpPacket import RtpPacket 
from aux_files.aux_message import Message, MsgType
from config import NODE_TCP_PORT, NODE_RTP_PORT, BOOTSTRAPPER_PORT, HEARTBEAT_INTERVAL, FAIL_TIMEOUT, MAX_FAILS

# These are not used, but are kept for compatibility with the ClientGUI.
CACHE_FILE_NAME = "cache-" 
CACHE_FILE_EXT = ".jpg" 

class ControlClient():
    """
    Client: Manages the network (TCP) and receives the video (UDP).
    """       
    
    def __init__(self, node_id, node_ip, bootstrapper_ip, video):
        self.node_id = node_id
        self.node_ip = node_ip
        self.bootstrapper_ip = bootstrapper_ip
        self.TCPport = NODE_TCP_PORT
        self.UDPport = NODE_RTP_PORT
        self.RTPport = NODE_RTP_PORT
        self.rtspSeq = 0
        self.frameNbr = 0
        self.neighbors = {}
        self.gui_callback = None
        
        # --- Settings RTP (UDP) ---
        self.RTPport = NODE_RTP_PORT 
        self.rtp_socket = None
        self.video = video 
        self.sessionId = 0
        self.frameNbr = 0
        
        self.neighbors = {} 
        self.last_alive = {} 
        self.fail_count = {} 
        
        #  Register and get neighbors
        self.register_and_join() 
        
        #  Start TCP Listener (Control)
        threading.Thread(target=self.listener_tcp, daemon=True).start()

        # Start UDP Listener (RTP/Video)
        self.open_rtp_port()

    # -------------------------------------------------------------------------
    # MANAGEMENT RTP (UDP)
    # -------------------------------------------------------------------------
    def open_rtp_port(self):
        """Opens the UDP socket to receive the video."""
        try:
            self.rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.rtp_socket.settimeout(0.5) 
            self.rtp_socket.bind((self.node_ip, self.RTPport))
            print(f"[Cliente] À escuta de RTP (Vídeo) em {self.node_ip}:{self.RTPport}")
        except Exception as e:
            print(f"[Cliente] Erro ao abrir socket RTP: {e}")

    def listen_rtp(self, gui_update_callback=None):
        """Receives RTP and sends the image IN MEMORY to the GUI."""
        while True:
            try:
                data, addr = self.rtp_socket.recvfrom(20480)
                
                if data:
                    rtpPacket = RtpPacket()
                    rtpPacket.decode(data)
                    
                    payload = rtpPacket.getFramePayload()
                    currFrameNbr = rtpPacket.seqNum()
                    
                    # Accept if it's greater (normal sequence)
                    # OR if the difference is very large (indicates video restarted or switched to a reset source)
                    if currFrameNbr > self.frameNbr or (self.frameNbr - currFrameNbr > 100):
                        self.frameNbr = currFrameNbr
                        
                        if len(payload) > 0:
                            if gui_update_callback:
                                try:
                                    gui_update_callback(payload)
                                except Exception as e:
                                    print(f"[GUI] Erro frame {currFrameNbr}: {e}")
                    
            except socket.timeout:
                continue
            except Exception as e:
                break

    def write_frame(self, data):
        """Writes the payload (JPEG image) to a temporary file."""
        cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        with open(cachename, "wb") as file:
            file.write(data)
        return cachename

    def get_neighbors(self):
        return self.neighbors
            
    def register_and_join(self):
        print(f"[Cliente] A registar {self.node_ip}...")
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(5.0)
            client.connect((self.bootstrapper_ip, BOOTSTRAPPER_PORT))
            
            message = Message.create_register_message(self.node_ip, self.bootstrapper_ip)
            client.sendall(message.to_bytes())
            
            response_raw = client.recv(4096).decode()
            client.close()
            
            data = Message.from_json(response_raw)
            neighbors = data.get_payload().get("neighbours", []) if data else []
            
            print(f"[Cliente] Vizinhos: {neighbors}")
            for neigh in neighbors:
                join_msg = Message.create_join_message(self.node_ip, neigh)
                active = self.send_tcp_message(neigh, join_msg)                
                self.neighbors[neigh] = True if active else False
                if active: self.last_alive[neigh] = time.time()
                
        except Exception as e:
            print(f"[Cliente] Erro Bootstrapper: {e}")

    def send_tcp_message(self, dest_ip, message):
        try:
            msg = message.to_bytes() if isinstance(message, Message) else Message.from_dict(message).to_bytes()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(2.0) 
                sock.connect((dest_ip, NODE_TCP_PORT)) 
                sock.sendall(msg)
            return True
        except:
            return False

    def listener_tcp(self):
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((self.node_ip, self.TCPport))
            server_socket.listen(5)
            while True:
                conn, addr = server_socket.accept()
                threading.Thread(target=self._handle_connection, args=(conn, addr), daemon=True).start()
        except Exception as e:
            print(f"[Cliente] Erro Listener TCP: {e}")

    def _handle_connection(self, conn, addr):
        try:
            while True:
                raw = conn.recv(65535)
                if not raw: break
                msg = Message.from_bytes(raw)
                if msg: self.handle_message(msg)
        except: pass
        finally: conn.close()

    def handle_message(self, msg):
        msg_type = msg.get_type()
        sender_ip = msg.get_src()
        if msg_type == MsgType.ALIVE:
            self.last_alive[sender_ip] = time.time()
            if sender_ip in self.neighbors: self.neighbors[sender_ip] = True
        elif msg_type == MsgType.JOIN:
            self.neighbors[sender_ip] = True
        elif msg_type == MsgType.LEAVE:
            print(f"[Cliente] Recebido LEAVE de {sender_ip}")
            if sender_ip in self.neighbors:
                self.neighbors[sender_ip] = False
        elif msg_type == MsgType.PING_TEST:
            self.handle_pingtest_message(msg)
            

        elif msg_type == MsgType.PONG:
            print(f"[Cliente] Recebi PONG de {sender_ip}")
            if hasattr(self, "gui_callback") and self.gui_callback:
                self.gui_callback("PONG RECEBIDO")
    
            if sender_ip in self.neighbors: self.neighbors[sender_ip] = False

    def handle_pingtest_message(self, msg):
        """
        Handles PING_TEST at the client (endpoint).
        It finalizes the path and displays the result.
        """
        payload = msg.get_payload()
        video_name = payload.get("video")
        path_so_far = payload.get("path", [])

        # Add current node (End of Line) to the path
        full_path = path_so_far + [self.node_id]
        path_string = " -> ".join(full_path)

        print(f"[Cliente]PING RECEBIDO com sucesso para '{video_name}'!")
        print(f"[Cliente]Rota Completa: {path_string}")



    def heartbeat(self):
        while True:
            time.sleep(HEARTBEAT_INTERVAL)
            for neigh, is_active in list(self.neighbors.items()):
                if is_active:
                    self.send_tcp_message(neigh, Message.create_alive_message(self.node_ip, neigh))
    
    def stop_stream(self):
        """Sends a request to stop the stream for ALL active neighbors."""
        if not self.video:
            return

        print(f"[Cliente] A enviar TEARDOWN para fechar stream {self.video}...")
        
        msg = Message(
            msg_type=MsgType.TEARDOWN, 
            srcip=self.node_ip, 
            # O destip aqui será preenchido no loop
            destip="", 
            payload={"video": self.video}
        )

        # Enviar para TODOS os vizinhos ativos para garantir que a rota fecha
        for neigh_ip, active in self.neighbors.items():
            if active:
                msg.destip = neigh_ip # Atualizar destino
                self.send_tcp_message(neigh_ip, msg)
                
                

if __name__ == "__main__":    
    if len(sys.argv) < 4:
        print("Use: python3 control_client.py NODE_ID NODE_IP BOOTSTRAPPER_IP [VIDEO]")
        sys.exit(1)
        
    node_id = sys.argv[1]
    node_ip = sys.argv[2]
    boot_ip = sys.argv[3]
    video = sys.argv[4] if len(sys.argv) > 4 else None    
    
    client = ControlClient(node_id, node_ip, boot_ip, video)
    
    threading.Thread(target=client.heartbeat, daemon=True).start()
    
    
    # Criar GUI
    root = Tk()
    app = ClienteGUI(root, client)
    root.title(f"Cliente RTP - {node_id}")
    root.mainloop()