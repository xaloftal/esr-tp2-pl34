import socket
import threading

connected_nodes = []  # lista de (ip, port)

def handle_node(conn, addr):
    global connected_nodes
    print(f"[BOOT] Node connected: {addr}")

    # Adiciona o novo node
    connected_nodes.append(addr)

    # Construir ring
    ring = {}
    total = len(connected_nodes)
    for i, node in enumerate(connected_nodes):
        prev_node = connected_nodes[(i - 1) % total]
        next_node = connected_nodes[(i + 1) % total]
        ring[node] = (prev_node, next_node)

    # Enviar ao node apenas os seus vizinhos
    neighbors = ring[addr]
    conn.send(str(neighbors).encode())

    conn.close()

def bootstrapper_server(host="0.0.0.0", port=5000):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen()

    print(f"[BOOT] Bootstrapper running on {host}:{port}")

    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_node, args=(conn, addr))
        thread.start()

def stream_video(video_path, neighbors):
    with open(video_path, "rb") as f:
        while chunk := f.read(1024):
            for ip, port in neighbors:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.sendto(chunk, (ip, port))


if __name__ == "__main__":
    bootstrapper_server()
