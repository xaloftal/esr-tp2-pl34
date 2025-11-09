import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Node.control_client import register_with_bootstrapper

def start_node(node_ip):
    print(f"[NODE {node_ip}] Starting node...")

    # Passo 1: contactar bootstrapper
    neighbors = register_with_bootstrapper(node_ip)
    print(f"[NODE {node_ip}] Received neighbors: {neighbors}")

    # Passo 2: abrir servidor  → receber HELLO
    # Passo 3: criar threads de envio de HELLO para cada vizinho

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 node.py <node_ip>")
        sys.exit(1)

    node_ip = sys.argv[1]
    start_node(node_ip)
