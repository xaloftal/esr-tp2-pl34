NODE 
import socket, threading, time
from control_protocol_pb2 import ControlMessage

BOOTSTRAPPER_IP = "127.0.0.1"
BOOTSTRAPPER_PORT = 5000

class Node:
    def __init__(self, node_id, ip, control_port=5001, data_port=5002):
        self.node_id = node_id
        self.ip = ip
        self.control_port = control_port
        self.data_port = data_port
        self.neighbors = {}

    def register_with_bootstrapper(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((BOOTSTRAPPER_IP, BOOTSTRAPPER_PORT))

        msg = ControlMessage()
        msg.type = ControlMessage.REGISTER
        msg.node_id = self.node_id
        msg.node_ip = self.ip
        msg.control_port = self.control_port
        msg.data_port = self.data_port

        s.sendall(b'\x01' + msg.SerializeToString())

        header = s.recv(1)
        data = s.recv(4096)
        if header == b'\x01':
            response = ControlMessage()
            response.ParseFromString(data)
            print(f"[{self.node_id}] Neighbors received:")
            for n in response.neighbors:
                print(f"   -> {n.node_id} ({n.node_ip})")
                self.neighbors[n.node_ip] = n
        s.close()

    def send_acks(self):
        while True:
            for ip, n in self.neighbors.items():
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    ack = ControlMessage()
                    ack.type = ControlMessage.ACK
                    ack.node_id = self.node_id
                    ack.node_ip = self.ip
                    s.sendto(b'\x01' + ack.SerializeToString(), (ip, n.data_port))
                    print(f"[{self.node_id}] Sent ACK to {n.node_id}")
            time.sleep(10)

    def start(self):
        self.register_with_bootstrapper()
        threading.Thread(target=self.send_acks, daemon=True).start()

if __name__ == "__main__":
    node = Node("Node-1", "127.0.0.1")
    node.start()
    while True:
        time.sleep(1)