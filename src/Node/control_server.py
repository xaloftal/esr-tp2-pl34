# control_server.py
import socket
import threading

class ControlServer:
    def __init__(self, node_id, node_ip, control_port):
        self.node_id = node_id
        self.node_ip = node_ip
        self.control_port = control_port

    def start(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.node_ip, self.control_port))
        server.listen()
        print(f"[{self.node_id}] listening on {self.node_ip}:{self.control_port}")

        while True:
            conn, addr = server.accept()
            threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()

    def handle_client(self, conn, addr):
        try:
            data = conn.recv(1024).decode()
            if data:
                print(f"[{self.node_id}] recebeu de {addr}: {data}")
        except Exception as e:
            print(f"[{self.node_id}] erro a receber: {e}")
        finally:
            conn.close()