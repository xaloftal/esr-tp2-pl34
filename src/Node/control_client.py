# control_client.py
import socket, pickle

BOOTSTRAP_IP = "127.0.0.1"
BOOTSTRAP_PORT = 5000

def register_node(node_id, node_ip, control_port):
    """Regista o nó no bootstrapper (sem pedir vizinhos)."""
    msg = {
        "type": "REGISTER",
        "node_id": node_id,
        "node_ip": node_ip,
        "control_port": control_port,
    }
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((BOOTSTRAP_IP, BOOTSTRAP_PORT))
        s.sendall(pickle.dumps(msg))
    print(f"[{node_id}] registado no bootstrapper.")

def send_message(ip, port, msg):
    """Envia uma mensagem a outro nó."""
    data = pickle.dumps(msg)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((ip, port))
        s.sendall(data)
