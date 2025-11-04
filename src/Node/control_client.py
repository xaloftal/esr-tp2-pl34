import socket
import Bootstrapper.config as config

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
