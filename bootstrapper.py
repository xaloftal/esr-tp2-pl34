import socket, threading
from control_protocol_pb2 import ControlMessage, Neighbor

BOOTSTRAPPER_PORT = 5000
nodes = {}  # ip -> (id, ports)

from control_protocol_pb2 import ControlMessage
import socket

BOOTSTRAPPER_IP = "127.0.0.1"
BOOTSTRAPPER_PORT = 5000

class Bootstrapper:
    def __init__(self):
        # Dicionário dos nós registados: { node_id: {...info...} }
        self.nodes = {}
        self.lock = threading.Lock()

    def start(self):
        """Inicia o servidor TCP para registo dos nós"""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((BOOTSTRAPPER_IP, BOOTSTRAPPER_PORT))
        s.listen(5)
        print(f"[Bootstrapper] Listening on {BOOTSTRAPPER_IP}:{BOOTSTRAPPER_PORT}")

        while True:
            conn, addr = s.accept()
            threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()

    def handle_client(self, conn, addr):
        """Trata de um pedido de registo de um nó"""
        try:
            header = conn.recv(1)
            if not header:
                conn.close()
                return

            data = conn.recv(4096)
            if not data:
                conn.close()
                return

            if header == b'\x01':  # ControlMessage
                msg = ControlMessage()
                msg.ParseFromString(data)
                if msg.type == ControlMessage.REGISTER:
                    self.handle_register(msg, conn, addr)
                else:
                    print(f"[Bootstrapper] Unknown message type {msg.type} from {addr}")
        except Exception as e:
            print(f"[Bootstrapper] Error handling client {addr}: {e}")
        finally:
            conn.close()

    def handle_register(self, msg, conn, addr):
        """Regista o nó e devolve a lista de vizinhos"""
        print(f"[Bootstrapper] Node registered: {msg.node_id} ({msg.node_ip})")

        # Guarda o nó na tabela
        with self.lock:
            self.nodes[msg.node_id] = {
                "node_id": msg.node_id,
                "ip": msg.node_ip,
                "control_port": msg.control_port,
                "data_port": msg.data_port
            }

        # Cria mensagem de resposta
        resp = ControlMessage()
        resp.type = ControlMessage.REGISTER_RESPONSE

        # Adiciona todos os outros nós como vizinhos
        with self.lock:
            for node_id, info in self.nodes.items():
                if node_id != msg.node_id:
                    n = resp.neighbors.add()
                    n.node_id = node_id
                    n.node_ip = info["ip"]
                    n.control_port = info["control_port"]
                    n.data_port = info["data_port"]

        # Envia resposta
        conn.sendall(b'\x01' + resp.SerializeToString())

        # Mostrar estado atual
        self.print_nodes()

    def print_nodes(self):
        """Mostra todos os nós registados"""
        with self.lock:
            print(f"\n[Bootstrapper] Nodes currently registered ({len(self.nodes)}):")
            for n in self.nodes.values():
                print(f"  - {n['node_id']} @ {n['ip']} (C:{n['control_port']} D:{n['data_port']})")
            print("")

if __name__ == "__main__":
    b = Bootstrapper()
    b.start()