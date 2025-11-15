import socket
import sys
import json
import uuid
import time


class ControlServer:

    def __init__(self, node_id, node_ip, bootstrap_ip, bootstrap_port=5000, tcp_port=6000):
        self.node_id = node_id
        self.node_ip = node_ip
        self.bootstrap_ip = bootstrap_ip
        self.bootstrap_port = bootstrap_port
        self.tcp_port = tcp_port

        # Dicionário de vizinhos
        self.neighbors = {}   # {ip: last_seen_timestamp}

    # ============================================================
    # REGISTER NO BOOTSTRAPPER
    # ============================================================
    def register_node(self):
        msg = f"REGISTER {self.node_ip}"

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.bootstrap_ip, self.bootstrap_port))
                s.sendall(msg.encode())

                response = s.recv(1024).decode()
                data = json.loads(response)

                print(f"[SERVER {self.node_id}] Registered at bootstrapper. Neighbors: {data['neighbors']}")

                now = time.time()
                for n in data["neighbors"]:
                    self.neighbors[n] = now

        except Exception as e:
            print(f"[SERVER {self.node_id}] Error registering: {e}")

    # ============================================================
    # FLOOD
    # ============================================================
    def initiate_flood(self):
        flood_id = str(uuid.uuid4())

        print(f"[SERVER {self.node_id}] Initiating flood ID={flood_id}")

        msg = {
            "type": "FLOOD",
            "id": flood_id,
            "src": self.node_id
        }

        for neighbor_ip in self.neighbors:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((neighbor_ip, self.tcp_port))
                    s.sendall(json.dumps(msg).encode())

                print(f"[SERVER {self.node_id}] Flood sent to {neighbor_ip}")

            except Exception as e:
                print(f"[SERVER {self.node_id}] Error sending flood to {neighbor_ip}: {e}")

    # ============================================================
    # STREAM
    # ============================================================
    def start_stream(self, dest_ip, stream_id="default"):
        msg = {
            "type": "STREAM_START",
            "stream_id": stream_id,
            "src": self.node_id
        }

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((dest_ip, self.tcp_port))
                s.sendall(json.dumps(msg).encode())

            print(f"[SERVER {self.node_id}] STREAM_START sent to {dest_ip}")

        except Exception as e:
            print(f"[SERVER {self.node_id}] Error starting stream: {e}")

    # ============================================================
    # MAIN COMMAND LOOP
    # ============================================================
    def run(self):
        print(f"[SERVER {self.node_id}] Ready.")

        while True:
            cmd = input(f"[SERVER {self.node_id}] Enter command (flood/stream/exit): ").strip().lower()

            if cmd == "flood":
                self.initiate_flood()

            elif cmd.startswith("stream"):
                parts = cmd.split()
                if len(parts) >= 2:
                    dest_ip = parts[1]
                    self.start_stream(dest_ip)
                else:
                    print("Usage: stream <dest_ip>")

            elif cmd == "exit":
                print(f"[SERVER {self.node_id}] Exiting server…")
                break

            else:
                print("Commands: flood | stream <dest_ip> | exit")


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python3 control_server.py NODE_ID NODE_IP BOOTSTRAPPER_IP")
        sys.exit(1)

    node_id = sys.argv[1]
    node_ip = sys.argv[2]
    bootstrap_ip = sys.argv[3]

    server = ControlServer(node_id, node_ip, bootstrap_ip)

    server.register_node()
    server.run()
