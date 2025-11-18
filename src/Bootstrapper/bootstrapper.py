# Ficheiro: src/Bootstrapper/bootstrapper.py
import socket
import threading
import json
from config import HOST, PORT
from overlay_nodes import node_overlay  # Importa o mapa

def handle_client(client_socket):
    try:
        request = client_socket.recv(1024).decode().strip()
        print(f"[BOOT] Received: {request}")
        print(f"[BOOT] Bootstrapper HOST is: {HOST}")

        if request.startswith("REGISTER"):
            parts = request.split()
            print(f"[BOOT] Parts received: {parts}")
            
            if len(parts) >= 2:
                node_ip = parts[1] 
                print(f"[BOOT] IP a procurar: {node_ip}")
                
                neighbors = node_overlay.get(node_ip, [])
                response_obj = {"neighbors": neighbors}
                
                print(f"[BOOT] Resposta: {response_obj}")
            else:
                response_obj = {"neighbors": []}

            response = json.dumps(response_obj)
            client_socket.sendall(response.encode())
        else:
            response = json.dumps({"status": "OK", "message": "ACK from Bootstrapper"})
            client_socket.sendall(response.encode())
    except Exception as e:
        print(f"[BOOT] Error handling client: {e}")
    finally:
        client_socket.close()

def bootstrapper_server(host, port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen()
    print(f"[BOOT] Bootstrapper running on {host}:{port}")

    try:
        while True:
            client_socket, addr = server.accept()
            print(f"[BOOT] Accepted connection from {addr}")
            client_handler = threading.Thread(target=handle_client, args=(client_socket,))
            client_handler.start()
    except KeyboardInterrupt:
        print("\n[BOOT] Shutting down server...")
    finally:
        server.close()

if __name__ == "__main__":
    bootstrapper_server(HOST, PORT)