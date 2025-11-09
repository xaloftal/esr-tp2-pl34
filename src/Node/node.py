# node.py
import sys, os
import threading
import time
from control_client import register_with_bootstrapper, send_message
from control_server import ControlServer
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Bootstrapper')))

from overlay_nodes import node_overlay  # ajusta o caminho se precisares

def start_node(node_id, node_ip, control_port):
    print(f"[{node_id}] a iniciar...")

    #  Registar no bootstrapper
    register_with_bootstrapper(node_ip)

    # Iniciar servidor antes de enviar
    server = ControlServer(node_id, node_ip, control_port)
    threading.Thread(target=server.start, daemon=True).start()
    time.sleep(5)  # tempo para garantir que o servidor está mesmo a ouvir

    # Carregar vizinhos
    if node_ip in node_overlay:
        neighbors = node_overlay[node_ip]
    else:
        neighbors = []
    print(f"[{node_id}] vizinhos: {neighbors}")

    # Enviar mensagens de teste
    for neighbor_ip in neighbors:
        msg = f"Olá do {node_id} para {neighbor_ip}"
        print(f"[{node_id}] a enviar para {neighbor_ip}: {msg}")
        send_message(neighbor_ip, control_port, msg)

    # manter o nó vivo
    print(f"[{node_id}] pronto e à escuta.")
    while True:
        time.sleep(1)

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Uso: python3 node.py <node_id> <node_ip> <control_port>")
        sys.exit(1)
    node_id, node_ip, control_port = sys.argv[1], sys.argv[2], int(sys.argv[3])
    start_node(node_id, node_ip, control_port)