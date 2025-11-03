import socket
import threading
import time

connected_nodes = []  # lista de (ip, port)

def handle_node(conn, addr):
    global connected_nodes
    print(f"[BOOT] Node connected: {addr}")

    connected_nodes.append(addr)

    # Construir anel (cada nó tem anterior e seguinte)
    ring = {}
    total = len(connected_nodes)
    for i, node in enumerate(connected_nodes):
        prev_node = connected_nodes[(i - 1) % total]
        next_node = connected_nodes[(i + 1) % total]
        ring[node] = (prev_node, next_node)

    # Enviar vizinhos ao novo nó
    neighbors = ring[addr]
    conn.send(str(neighbors).encode())
    conn.close()

    # Assim que houver pelo menos 2 nós, começa a enviar o vídeo
    if len(connected_nodes) > 1:
        print("[BOOT] A iniciar streaming de vídeo...")
        stream_video("videoRonaldo.mov", [connected_nodes[1]])

def stream_video(video_path, neighbors):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"[BOOT] A enviar {video_path} para {neighbors} ...")

    try:
        with open(video_path, "rb") as f:
            chunk = f.read(4096)
            while chunk:
                for ip, port in neighbors:
                    sock.sendto(chunk, (ip, port))
                time.sleep(0.04)  # ~25 FPS
                chunk = f.read(4096)
        print("[BOOT] Fim do vídeo.")
    except FileNotFoundError:
        print(f"[ERRO] Ficheiro {video_path} não encontrado!")
    finally:
        sock.close()

def bootstrapper_server(host="0.0.0.0", port=5000):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen()
    print(f"[BOOT] Bootstrapper running on {host}:{port}")

    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_node, args=(conn, addr))
        thread.start()

if __name__ == "__main__":
    bootstrapper_server()
