# Ficheiro: src/Node/control_client.py
import json
import socket
import threading
import sys
from tkinter import Tk
from aux_files.ClienteGUI import ClienteGUI

from aux_files.aux_message import Message, MsgType
from config import NODE_TCP_PORT, NODE_RTP_PORT, RTP_PORT,  BOOTSTRAPPER_PORT


class ControlClient():
    """Cliente para visualizar videos RTP
        Diferente de Node. Não herda nada.
    """       
    
    def __init__(self, node_id, node_ip, bootstrapper_ip, videos):
        self.node_id = node_id
        self.node_ip = node_ip
        self.bootstrapper_ip = bootstrapper_ip
        self.TCPport = NODE_TCP_PORT
        self.UDPport = NODE_RTP_PORT
        self.RTPport = RTP_PORT
        self.rtspSeq = 0
        self.frameNbr = 0
        self.neighbors = {}
        self.register_and_join()  # vizinhos ativos
        
        # video(s) que quer ver
        self.videos = videos


    def get_neighbors(self):
        return self.neighbors
            
            
    def register_and_join(self):
        """
        ETAPA 1: Regista o nó no bootstrapper e obtém a lista de vizinhos.
        """
        print(f"[Cliente] A tentar registar com o IP: {self.node_ip}")
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(5.0)
            client.connect((self.bootstrapper_ip, BOOTSTRAPPER_PORT))
            print(f"[Cliente] Ligado ao Bootstrapper em {self.bootstrapper_ip}:{BOOTSTRAPPER_PORT}")

            # Envia a mensagem de registo
            message = Message.create_register_message(self.node_ip, self.bootstrapper_ip)
            client.sendall(message.to_bytes())

            # Recebe a resposta (JSON com a lista de vizinhos)
            response_raw = client.recv(4096).decode()
            client.close()

            data = Message.from_json(response_raw)
            if not data:
                print(f"[Cliente] Falha a parsear resposta do bootstrapper: {response_raw}")
                return []
                
            neighbors = data.get_payload().get("neighbours", [])
            
            print(f"[Cliente] Vizinhos recebidos do bootstrapper: {neighbors}")

            for neigh in neighbors:
                join_msg = Message.create_join_message(self.node_ip, neigh)

                active = self.send_tcp_message(neigh, join_msg)
                
                # if there's a connection, add the neighbour with True
                self.neighbors[neigh] = True if active else False
        
        except json.JSONDecodeError:
            print(f"[Cliente] Falha a parsear resposta do bootstrapper: {response_raw}")
            return []
        except Exception as e:
            print(f"[Cliente] Erro a ligar/registar no bootstrapper: {e}")
            return []

    def send_tcp_message(self, dest_ip, message):
            """
            Envia uma mensagem de controlo (Message object) para um nó vizinho.
            """
            try:
                msg = message.to_bytes() if isinstance(message, Message) else Message.from_dict(message).to_bytes()
                
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(2.0) # Timeout curto para não bloquear
                    
                    # Cada nó escuta na mesma porta de controlo
                    sock.connect((dest_ip, NODE_TCP_PORT)) 
                    sock.sendall(msg)
                return True

            except: #Exception as e:
                # print(f"[Cliente] Erro a enviar TCP para {dest_ip}:{NODE_TCP_PORT}: {e}")
                return 

if __name__ == "__main__":    
    if len(sys.argv) < 4:
        print("Uso: python3 control_client.py NODE_ID NODE_IP BOOTSTRAPPER_IP [VIDEO]")
        sys.exit(1)
        
    node_id = sys.argv[1]
    node_ip = sys.argv[2]
    boot_ip = sys.argv[3]
    video = sys.argv[4] if len(sys.argv) > 4 else None    
    
    # Criar ControlClient wrapper
    client = ControlClient(node_id, node_ip, boot_ip, video)
    
    # Criar GUI
    root = Tk()
    app = ClienteGUI(root, client)
    root.title(f"Cliente RTP - {node_id}")
    root.mainloop()
