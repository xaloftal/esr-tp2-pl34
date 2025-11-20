# Ficheiro: src/Node/control_client.py
import socket
import json
import time
from config import BOOTSTRAPPER_IP, BOOTSTRAPPER_PORT, NODE_TCP_PORT

def register_with_bootstrapper(node_ip):
    """
    ETAPA 1: Regista o nó no bootstrapper e obtém a lista de vizinhos.
    """
    print(f"[Cliente] A tentar registar com o IP: {node_ip}")
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(5.0)
        client.connect((BOOTSTRAPPER_IP, BOOTSTRAPPER_PORT))
        print(f"[Cliente] Ligado ao Bootstrapper em {BOOTSTRAPPER_IP}:{BOOTSTRAPPER_PORT}")

        # Envia a mensagem de registo
        message = f"REGISTER {node_ip}\n"
        client.sendall(message.encode())

        # Recebe a resposta (JSON com a lista de vizinhos)
        response_raw = client.recv(4096).decode()
        client.close()

        data = json.loads(response_raw)
        neighbors = data.get("neighbors", [])
        
        print(f"[Cliente] Vizinhos recebidos do bootstrapper: {neighbors}")
        return neighbors
    
    except json.JSONDecodeError:
        print(f"[Cliente] Falha a parsear resposta do bootstrapper: {response_raw}")
        return []
    except Exception as e:
        print(f"[Cliente] Erro a ligar/registar no bootstrapper: {e}")
        return []

def send_tcp_message(dest_ip, msg_dict):
    """
    Envia uma mensagem de controlo (dicionário Python) para um nó vizinho.
    """
    try:
        payload = json.dumps(msg_dict).encode()
        
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(2.0) # Timeout curto para não bloquear
            
            # Cada nó escuta na mesma porta de controlo
            sock.connect((dest_ip, NODE_TCP_PORT)) 
            sock.sendall(payload)
        return True

    except: #Exception as e:
        # print(f"[Cliente] Erro a enviar TCP para {dest_ip}:{NODE_TCP_PORT}: {e}")
        return #False