# node.py
import uuid, threading
from control_server import ControlServer
import control_client

class Node:
    def __init__(self, node_id, node_ip, control_port):
        self.node_id = node_id
        self.node_ip = node_ip
        self.control_port = control_port
        self.neighbors = []  # lista de dicts: {"node_id": ..., "node_ip": ..., "control_port": ...}
        self.received_msgs = set()

    def start(self):
        # 1️⃣ arranca o servidor
        threading.Thread(target=ControlServer(self).start, daemon=True).start()

        # 2️⃣ regista-se no bootstrapper
        control_client.register_node(self.node_id, self.node_ip, self.control_port)

    # adicionar vizinho manualmente
    def add_neighbor(self, node_id, node_ip, control_port):
        self.neighbors.append({
            "node_id": node_id,
            "node_ip": node_ip,
            "control_port": control_port
        })
        print(f"[{self.node_id}] adicionou vizinho {node_id}@{node_ip}:{control_port}")

    def send_message(self, target, content):
        msg = {
            "type": "HELLO",
            "msg_id": str(uuid.uuid4()),
            "source": self.node_id,
            "target": target,
            "content": content,
            "path": [self.node_id],
        }
        self.received_msgs.add(msg["msg_id"])
        self.broadcast(msg)

    def broadcast(self, msg):
        for n in self.neighbors:
            try:
                control_client.send_message(n["node_ip"], n["control_port"], msg)
            except Exception as e:
                print(f"[{self.node_id}] erro a enviar para {n['node_id']}: {e}")

    def forward_message(self, msg):
        msg["path"] = msg.get("path", []) + [self.node_id]
        for n in self.neighbors:
            if n["node_id"] not in msg["path"]:
                try:
                    control_client.send_message(n["node_ip"], n["control_port"], msg)
                except Exception:
                    pass
