import socket

HOST = '10.0.1.10'      # escuta em todas as interfaces
PORT = 5000

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((HOST, PORT))
    s.listen()
    print("Servidor a ouvir em", PORT)
    conn, addr = s.accept()
    with conn:
        print("Ligação de", addr)
        while True:
            data = conn.recv(1024)
            if not data:
                break
            print("Recebido:", data.decode())
            conn.sendall(b"HELLO CLIENT")
            import socket
