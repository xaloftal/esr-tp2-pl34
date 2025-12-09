# Ficheiro: src/Node/control_client.py
import json
import socket
import threading
import sys
import time
import os
from tkinter import Tk
from aux_files.ClienteGUI import ClienteGUI
from aux_files.RtpPacket import RtpPacket 
from aux_files.aux_message import Message, MsgType
from config import NODE_TCP_PORT, NODE_RTP_PORT, BOOTSTRAPPER_PORT, HEARTBEAT_INTERVAL, FAIL_TIMEOUT, MAX_FAILS

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class ControlClient():
    """
    Cliente: Gere a rede (TCP) e recebe o vídeo (UDP).
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
        self.register_and_join()  # vizinhos ativos
        self.gui_callback = None
        
        # --- Configuração RTP (UDP) ---
        self.RTPport = NODE_RTP_PORT 
        self.rtp_socket = None
        self.video = video 
        self.sessionId = 0
        self.frameNbr = 0
        
        self.neighbors = {} 
        self.last_alive = {} 
        self.fail_count = {} 
        
        #  Registar e obter vizinhos
        self.register_and_join() 
        
        #  Iniciar Listener TCP (Control)
        threading.Thread(target=self.listener_tcp, daemon=True).start()

        # Iniciar Listener UDP (RTP/Video)
        self.open_rtp_port()

    # -------------------------------------------------------------------------
    # GESTÃO RTP (UDP)
    # -------------------------------------------------------------------------
    def open_rtp_port(self):
        """Abre o socket UDP para receber o vídeo."""
        try:
            self.rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.rtp_socket.settimeout(0.5) 
            self.rtp_socket.bind((self.node_ip, self.RTPport))
            print(f"[Cliente] À escuta de RTP (Vídeo) em {self.node_ip}:{self.RTPport}")
        except Exception as e:
            print(f"[Cliente] Erro ao abrir socket RTP: {e}")

    def listen_rtp(self, gui_update_callback=None):
        while True:
            try:
                data, addr = self.rtp_socket.recvfrom(20480)
                
                if data:
                    rtpPacket = RtpPacket()
                    rtpPacket.decode(data)
                    
                    payload = rtpPacket.getPayload()
                    currFrameNbr = rtpPacket.seqNum()
                    
                    
                    if currFrameNbr > self.frameNbr:
                        self.frameNbr = currFrameNbr
                        
                        # Proteção: Só processa se tiver dados reais
                        if len(payload) > 0:
                            image_file = self.write_frame(payload)
                            
                            if gui_update_callback:
                                try:
                                    gui_update_callback(image_file)
                                except Exception as e:
                                    # Se a imagem for má, apenas ignoramos este frame e não matamos a thread
                                    print(f"[GUI] Frame {currFrameNbr} corrompido ou incompleto. Ignorar.")
                        
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[Cliente] RTP Interrompido: {e}")
                break
    def write_frame(self, data):
        """Escreve o payload (imagem JPEG) num ficheiro temporário."""
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
        elif msg_type == MsgType.PONG:
            print(f"[Cliente] Recebi PONG de {sender_ip}")
            if hasattr(self, "gui_callback") and self.gui_callback:
                self.gui_callback("PONG RECEBIDO")
    
            if sender_ip in self.neighbors: self.neighbors[sender_ip] = False

    def heartbeat(self):
        while True:
            time.sleep(HEARTBEAT_INTERVAL)
            for neigh, is_active in list(self.neighbors.items()):
                if is_active:
                    self.send_tcp_message(neigh, Message.create_alive_message(self.node_ip, neigh))
    
    def stop_stream(self):
        """Envia pedido para parar o stream antes de sair."""
        if not self.video:
            return

        
        gateway_ip = None
        for ip, active in self.neighbors.items():
            if active:
                gateway_ip = ip
                break
        
        if gateway_ip:
            print(f"[Cliente] A enviar TEARDOWN para {gateway_ip}...")
            msg = Message(
                msg_type=MsgType.TEARDOWN, 
                srcip=self.node_ip, 
                destip=gateway_ip,
                payload={"video": self.video}
            )
            self.send_tcp_message(gateway_ip, msg)

if __name__ == "__main__":    
    if len(sys.argv) < 4:
        print("Uso: python3 control_client.py NODE_ID NODE_IP BOOTSTRAPPER_IP [VIDEO]")
        sys.exit(1)
        
    node_id = sys.argv[1]
    node_ip = sys.argv[2]
    boot_ip = sys.argv[3]
    video = sys.argv[4] if len(sys.argv) > 4 else None    
    
    client = ControlClient(node_id, node_ip, boot_ip, video)
    
    threading.Thread(target=client.heartbeat, daemon=True).start()
    
    # 👉 INICIAR LISTENER TCP (FUNDAMENTAL)
    listener_thread = threading.Thread(target=client.listener_tcp, daemon=True)
    listener_thread.start()
    
    # Criar GUI
    root = Tk()
    app = ClienteGUI(root, client)
    root.title(f"Cliente RTP - {node_id}")
    root.mainloop()
