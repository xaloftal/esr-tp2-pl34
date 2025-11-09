# control_client.py
import os, sys
# adiciona o caminho da pasta Bootstrapper ao PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Bootstrapper')))

import socket
import config  # agora importa o config diretamente

# Função para registar o nó com o Bootstrapper
def register_with_bootstrapper(node_ip):
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect((config.HOST, config.PORT))
    print(f"[CTRL] Connected to Bootstrapper at {config.HOST}:{config.PORT}")

    # Envia o registo
    message = f"REGISTER {node_ip}"
    client.send(message.encode())

    # Recebe resposta
    response = client.recv(4096).decode()
    client.close()
    return response

def send_message(target_ip, target_port, message):
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect((target_ip, target_port))
        client.send(message.encode())
        client.close()
    except Exception as e:
        print(f"[CLIENT] erro a enviar para {target_ip}:{target_port} -> {e}")