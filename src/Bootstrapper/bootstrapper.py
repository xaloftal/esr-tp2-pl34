import socket
import threading
from config import HOST, PORT, N_vizinho
from overlay_nodes import node_overlay


def handle_client(client_socket):
    request = client_socket.recv(1024).decode().strip()
    print(f"[BOOT] Received: {request}")

    if request.startswith("REGISTER"):
        node_ip = request.split()[-1]  # extrai o IP depois de REGISTER

        # Lógica de vizinhos
        if node_ip in node_overlay:
            neighbors = node_overlay[node_ip]
            response = f"Neighbors: {neighbors}"
        else:
            response = "No neighbors assigned."

        client_socket.send(response.encode())
    else:
        client_socket.send(b"ACK from Bootstrapper")

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
