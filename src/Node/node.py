import threading
import time
import socket
from control_client import ControlClient
from control_server import ControlServer


class Node:
    def __init__(self, node_id, node_ip, control_port, target_ip, target_port):
        self.node_id = node_id
        self.node_ip = node_ip
        self.control_port = control_port
        self.target_ip = target_ip
        self.target_port = target_port

        self.client = ControlClient(node_ip, control_port)
        self.server = None
        self.server_thread = None
        self.running = True

    # --------------------------
    def start_server(self):
        if self.server_thread and self.server_thread.is_alive():
            print(f"[{self.node_id}] Servidor já está ativo.")
            return

        def run_server():
            self.server = ControlServer(self.node_id, self.node_ip, self.control_port)
            self.server.start()

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        time.sleep(0.5)
        print(f"[{self.node_id}] Servidor TCP iniciado em {self.node_ip}:{self.control_port}")

    # --------------------------
    def stop_server(self):
        if not self.server:
            print(f"[{self.node_id}] Servidor não está ativo.")
            return
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.node_ip, self.control_port))
                s.send(b"STOP")
            print(f"[{self.node_id}] Servidor parado com sucesso.")
        except Exception:
            print(f"[{self.node_id}] Não foi possível parar o servidor.")
        self.server = None

    # --------------------------
    def run_menu(self):
        print("\n=== MODO INTERATIVO ===")
        print("0 → Enviar mensagem")
        print("1 → Sair")
        print("2 → Iniciar servidor TCP (ficar à escuta)")
        print("3 → Parar servidor TCP\n")

        while self.running:
            choice = input(f"[{self.node_id}] Escolhe uma opção (0/1/2/3): ").strip()

            if choice == "0":
                msg = input("Mensagem a enviar: ")
                self.client.send_message(self.target_ip, self.target_port, msg)

            elif choice == "1":
                print(f"[{self.node_id}] A encerrar...")
                self.running = False
                self.stop_server()
                break

            elif choice == "2":
                self.start_server()

            elif choice == "3":
                self.stop_server()

            else:
                print("⚠️ Opção inválida. Usa 0, 1, 2 ou 3.")


def main():
    print("=== Configuração do Nó ===")
    node_id = input("ID do nó (ex: Node-1): ").strip()
    node_ip = input("IP local (ex: 127.0.0.1): ").strip()
    control_port = int(input("Porto local (ex: 5001): ").strip())
    target_ip = input("IP destino (ex: 127.0.0.1): ").strip()
    target_port = int(input("Porto destino (ex: 5002): ").strip())

    node = Node(node_id, node_ip, control_port, target_ip, target_port)
    node.client.register_with_bootstrapper()
    node.run_menu()


if __name__ == "__main__":
    main()
