# control_client.py
import os, sys, socket
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Bootstrapper')))
import config  # importa o ficheiro de configuração do bootstrapper


class ControlClient:
    """
    Cliente de controlo — comunica via TCP com o Bootstrapper e outros nós.
    Responsável por registo, envio de mensagens de controlo e gestão de vizinhos.
    """
    def __init__(self, node_ip, control_port=5001):
        self.node_ip = node_ip
        self.control_port = control_port
        self.bootstrapper_host = config.HOST
        self.bootstrapper_port = config.PORT
        self.neighbors = {}  # dicionário {ip: {'port': X, 'status': Y}}
        print(f"[INIT] ControlClient iniciado no IP {self.node_ip}, porto {self.control_port}")

    # Registo no Bootstrapper
    def register_with_bootstrapper(self):
        """
        Regista este nó no Bootstrapper via TCP.
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                client.connect((self.bootstrapper_host, self.bootstrapper_port))
                print(f"[CTRL] Conectado ao Bootstrapper em {self.bootstrapper_host}:{self.bootstrapper_port}")

                # envia mensagem de registo
                message = f"REGISTER {self.node_ip}"
                client.send(message.encode())

                # recebe resposta
                response = client.recv(4096).decode()
                print(f"[CTRL] Resposta do Bootstrapper: {response}")

                # processa resposta (exemplo: lista de vizinhos)
                if response.startswith("NEIGHBORS"):
                    neighbors_data = response.split()[1:]  # ex: "NEIGHBORS ip1,ip2"
                    for neighbor in neighbors_data:
                        ip, port = neighbor.split(":")
                        self.neighbors[ip] = {"port": int(port), "status": "active"}
                    print(f"[CTRL] Vizinhos registados: {self.neighbors}")

                return response

        except Exception as e:
            print(f"[ERROR] Falha ao registar no Bootstrapper: {e}")
            return None

    # Envio de Mensagens TCP
    def send_message(self, target_ip, target_port, message):
        """
        Envia uma mensagem TCP para outro nó.
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                client.connect((target_ip, target_port))
                client.send(message.encode())
                print(f"[TCP] Enviado para {target_ip}:{target_port} → {message}")
        except Exception as e:
            print(f"[ERROR] Erro a enviar para {target_ip}:{target_port}: {e}")


    # Receção de Mensagens TCP
    def start_tcp_server(self):
        """
        Cria um pequeno servidor TCP para receber mensagens de controlo de outros nós.
        """
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((self.node_ip, self.control_port))
        server.listen(5)
        print(f"[CTRL] Servidor de controlo ativo em {self.node_ip}:{self.control_port}")

        while True:
            conn, addr = server.accept()
            data = conn.recv(4096).decode()
            print(f"[RECEBIDO] {addr}: {data}")
            conn.close()

    # -----------------------------
    # 4️⃣ Envio de vídeo via UDP (exemplo futuro)
    def send_video_packet(self, target_ip, target_port, data):
        """
        Exemplo de envio de dados (frames de vídeo) via UDP.
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_sock:
                udp_sock.sendto(data, (target_ip, target_port))
                print(f"[UDP] Pacote de vídeo enviado para {target_ip}:{target_port}")
        except Exception as e:
            print(f"[ERROR] Falha ao enviar pacote UDP: {e}")


if __name__ == "__main__":
    client = ControlClient("localhost")  # ip do nó
    client.register_with_bootstrapper()
    client.send_message("localhost", 5001, "HELLO FROM CLIENT")
