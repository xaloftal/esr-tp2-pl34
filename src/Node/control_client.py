import sys
import socket
import uuid

class Client:
    def __init__(self, node_id, node_ip, bootstrapper_ip, bootstrapper_port=5000):
        self.node_id = node_id
        self.node_ip = node_ip
        self.bootstrapper_ip = bootstrapper_ip
        self.bootstrapper_port = bootstrapper_port

    def register(self):
        msg = f"REGISTER {self.node_ip}"
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.bootstrapper_ip, self.bootstrapper_port))
                s.sendall(msg.encode())
                response = s.recv(1024).decode()
                print(f"[CLIENT {self.node_id}] Received from Bootstrapper: {response}")
        except Exception as e:
            print(f"[CLIENT {self.node_id}] Error registering: {e}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python3 control_client.py NODE_ID NODE_IP BOOTSTRAPPER_IP")
        sys.exit(1)

    node_id = sys.argv[1]
    node_ip = sys.argv[2]
    bootstrap_ip = sys.argv[3]

    client = Client(node_id, node_ip, bootstrap_ip)
    client.register()