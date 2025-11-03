import socket

BOOTSTRAPPER_IP = "10.0.0.20"   # muda para o IP do boot no CORE
BOOTSTRAPPER_PORT = 5000

def join_overlay():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((BOOTSTRAPPER_IP, BOOTSTRAPPER_PORT))
    
    print("[NODE] Connected to Bootstrapper")

    data = s.recv(1024).decode()
    print("[NODE] Neighbors received:", data)

    s.close()

def listen_and_forward(my_port, neighbors):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", my_port))
    while True:
        data, _ = sock.recvfrom(1024)
        # reenviar para os vizinhos
        for ip, port in neighbors:
            sock.sendto(data, (ip, port))


if __name__ == "__main__":
    join_overlay()
