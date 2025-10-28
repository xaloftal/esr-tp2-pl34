import socket

HOST = '10.0.1.10'  # IP do servidor
PORT = 5000

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, PORT))
    s.sendall(b"HELLO SERVER")
    data = s.recv(1024)
    print("Resposta:", data.decode())
