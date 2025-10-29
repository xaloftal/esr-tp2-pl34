from control_protocol_pb2 import ControlMessage
import socket

BOOTSTRAPPER_IP = "127.0.0.1"
BOOTSTRAPPER_PORT = 5000

class Client:
    def __init__(self, client_id, client_ip):
        self.client_id = client_id
        self.ip = client_ip

    def register(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((BOOTSTRAPPER_IP, BOOTSTRAPPER_PORT))

        msg = ControlMessage()
        msg.type = ControlMessage.REGISTER
        msg.node_id = self.client_id
        msg.node_ip = self.ip
        msg.control_port = 5101
        msg.data_port = 5102

        s.sendall(b'\x01' + msg.SerializeToString())

        header = s.recv(1)
        data = s.recv(4096)
        if header == b'\x01':
            resp = ControlMessage()
            resp.ParseFromString(data)
            print(f"[Client] Registered. Neighbors:")
            for n in resp.neighbors:
                print(f"  - {n.node_id} ({n.node_ip})")
        s.close()

if __name__ == "__main__":
    client = Client("Client-1", "127.0.0.1")
    client.register()