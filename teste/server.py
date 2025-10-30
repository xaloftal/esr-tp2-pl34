import socket
import threading

HOST = '0.0.0.0'   # aceita ligações de qualquer IP
PORT = 8000        # certifica-te que o client usa a mesma porta

# Função que vai tratar cada cliente numa thread diferente
def handle_client(conn, addr):
    print(f"[NOVA LIGAÇÃO] Cliente ligado: {addr}")
    while True:
        data = conn.recv(1024)
        if not data:
            break
        print(f"[{addr}] Recebido: {data.decode()}")
        conn.sendall(b"HELLO CLIENT")  # resposta ao cliente
    conn.close()
    print(f"[LIGAÇÃO TERMINADA] {addr} desconectou")

# Servidor principal
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen()

    print(f"[SERVIDOR] A ouvir em {HOST}:{PORT}")

    while True:
        conn, addr = s.accept()  # espera por um cliente
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.start()
        print(f"[ATIVOS] Clientes ligados: {threading.active_count() - 1}")
