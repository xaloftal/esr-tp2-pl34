# control_server.py
import socket, threading, pickle

class ControlServer:
    def __init__(self, node):
        self.node = node

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((self.node.node_ip, self.node.control_port))
        sock.listen()
        print(f"[{self.node.node_id}] listening on {self.node.node_ip}:{self.node.control_port}")

        while True:
            conn, _ = sock.accept()
            threading.Thread(target=self.handle_conn, args=(conn,), daemon=True).start()

    def handle_conn(self, conn):
        try:
            data = conn.recv(65536)
            if not data:
                return
            msg = pickle.loads(data)
            if msg.get("type") == "HELLO":
                self.handle_hello(msg)
        except Exception as e:
            print(f"[{self.node.node_id}] erro a receber: {e}")
        finally:
            conn.close()

    def handle_hello(self, msg):
        msg_id = msg["msg_id"]
        if msg_id in self.node.received_msgs:
            return
        self.node.received_msgs.add(msg_id)

        target = msg["target"]
        source = msg["source"]
        content = msg["content"]

        if target == self.node.node_id:
            print(f"[{self.node.node_id}] recebeu de {source}: {content}")
        else:
            # reencaminhar para os vizinhos
            self.node.forward_message(msg)
