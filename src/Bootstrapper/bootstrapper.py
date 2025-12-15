# Ficheiro: src/Bootstrapper/bootstrapper.py
import socket
import threading
import sys
import json
import os

# Add parent directory to path to import from Node
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import HOST, PORT
from overlay_nodes import node_overlay_c1, node_overlay_c2, node_overlay_c3, node_overlay_c4, node_overlay_c5
from Node.aux_files.aux_message import Message


class Bootstrapper():
    def __init__(self, config):
        self.host = HOST 
        self.port = PORT  
        
        if config == "c2":
            self.map = node_overlay_c2
        elif config == "c1":
            self.map = node_overlay_c1
        elif config == "c4":
            self.map = node_overlay_c4
        elif config == "c5":
            self.map = node_overlay_c5
        else:
            self.map = node_overlay_c3
        
        
        print(f"[BOOT] Loaded configuration: {config}")
            
            
    def handle_client(self, client_socket, addr):
        """Handles client registration requests using Message class."""
        sender_ip = addr[0] 
        
        try:
            # Receive raw data
            raw_data = client_socket.recv(65535)
            if not raw_data:
                print(f"[BOOT] Empty request from {sender_ip}")
                return
            
            # Parse incoming message
            msg = Message.from_bytes(raw_data)
            
            if not msg:
                # Fallback for legacy plain text REGISTER messages
                request = raw_data.decode().strip()
                print(f"[BOOT] Legacy request from {sender_ip}: {request}")
                
                if request.startswith("REGISTER"):
                    parts = request.split()
                    if len(parts) >= 2:
                        node_ip = parts[1]
                        neighbors = self.map.get(node_ip, [])
                        response_obj = {"neighbors": neighbors}
                    else:
                        response_obj = {"neighbors": []}
                    
                    response = json.dumps(response_obj)
                    client_socket.sendall(response.encode())
                return
            
            msg_type = msg.get_type()
            payload = msg.get_payload()
            
            if msg_type == "REGISTER":
                # Extract node IP from srcip or payload
                node_ip = msg.get_src() or payload.get("node_id", sender_ip)
                print(f"[BOOT] Registration request for IP: {node_ip}")
                
                # Get neighbors from overlay map
                neighbors = self.map.get(node_ip, [])
                
                # Create response message
                resp_message = Message.create_neighbour_message(
                    srcip=self.host,
                    destip=node_ip,
                    neighbours_ip=neighbors
                )
                
                # Send response
                client_socket.sendall(resp_message.to_bytes())
                print(f"[BOOT] Sent neighbors to {node_ip}: {neighbors}")
                
            else:
                # Unknown message type - send ACK
                response_msg = Message(
                    msg_type="ACK",
                    srcip=self.host or "bootstrapper",
                    destip=sender_ip,
                    payload={"message": "Unknown message type"}
                )
                client_socket.sendall(response_msg.to_bytes())
                
        except Exception as e:
            print(f"[BOOT] Error handling client {sender_ip}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            client_socket.close()

    def start(self, host, port):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        server.listen()
        print(f"[BOOT] Bootstrapper running on {host}:{port}")

        try:
            while True:
                client_socket, addr = server.accept()
                print(f"[BOOT] Accepted connection from {addr}")
                client_handler = threading.Thread(target=self.handle_client, args=(client_socket, addr))
                client_handler.start()
        except KeyboardInterrupt:
            print("\n[BOOT] Shutting down server...")
        finally:
            server.close()

if __name__ == "__main__":    
    # Check command line arguments
    if len(sys.argv) != 2:
        print("Usage: python bootstrapper.py  CONFIG")
        print("  CONFIG:    Configuration name (c1, c2, or c3)")
        print("\nExample: python bootstrapper.py 192.168.1.1 c1")
        sys.exit(1)
    
    # Parse arguments
    config = sys.argv[1]
    
    # Validate config
    if config not in ["c1", "c2", "c3","c4","c5"]:
        print(f"Error: Invalid CONFIG '{config}'. Must be c1, c2, c3 or c5")
        sys.exit(1)
    
    # Create and start bootstrapper
    try:
        bootstrapper = Bootstrapper(config)
        bootstrapper.start(HOST, PORT)
        
    except Exception as e:
        print(f"[BOOT] Fatal error: {e}")
        sys.exit(1)