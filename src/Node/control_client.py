import socket
import threading
import json
import time
import Bootstrapper.config as config
from Node.node import Node


class Client(Node):
    """Classe para o cliente, herda da Node"""       
    
    def __init__(self, node_id, node_ip, bootstrapper_ip, bootstrapper_port, 
                 flood_port=6000, stream_port=1000, alive_port=2000):
        super().__init__(node_id, node_ip, bootstrapper_ip, bootstrapper_port,
                        flood_port, stream_port, alive_port)
    
    def start_flood_listener(self):
        """
        Listens for incoming flood messages on the flood port.
        """
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.node_ip, self.flood_port))
        server.listen()
        print(f"[{self.node_id}] FLOOD listener on {self.node_ip}:{self.flood_port}")

        while True:
            conn, addr = server.accept()
            threading.Thread(target=self.handle_flood_connection, args=(conn, addr), daemon=True).start()

    def start_stream_listener(self):
        """
        Listens for incoming stream requests/data on the stream port.
        """
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.node_ip, self.stream_port))
        server.listen()
        print(f"[{self.node_id}] STREAM listener on {self.node_ip}:{self.stream_port}")

        while True:
            conn, addr = server.accept()
            threading.Thread(target=self.handle_stream_connection, args=(conn, addr), daemon=True).start()

    def start_alive_listener(self):
        """
        Listens for incoming alive/heartbeat messages on the alive port.
        """
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.node_ip, self.alive_port))
        server.listen()
        print(f"[{self.node_id}] ALIVE listener on {self.node_ip}:{self.alive_port}")

        while True:
            conn, addr = server.accept()
            threading.Thread(target=self.handle_alive_connection, args=(conn, addr), daemon=True).start()

    def handle_flood_connection(self, conn, addr):
        """
        Handles incoming flood messages.
        """
        try:
            data = conn.recv(1024).decode()
            if data:
                print(f"[{self.node_id}] FLOOD received from {addr[0]}")
                
                try:
                    msg = json.loads(data)
                    if msg.get('type') == 'FLOOD':
                        flood_data = msg.get('data')
                        if flood_data:
                            # Process the flood and update routing table
                            should_forward = self.handle_flood_message(flood_data, addr[0])
                            
                            # Forward to other neighbors if this is a new flood
                            if should_forward:
                                self.forward_flood_message(flood_data, exclude_ip=addr[0])
                except json.JSONDecodeError:
                    print(f"[{self.node_id}] Invalid JSON in flood message")
                    
        except Exception as e:
            print(f"[{self.node_id}] Error handling flood: {e}")
        finally:
            conn.close()

    def handle_stream_connection(self, conn, addr):
        """
        Handles incoming stream requests or data.
        """
        try:
            data = conn.recv(1024).decode()
            if data:
                print(f"[{self.node_id}] STREAM message from {addr[0]}")
                
                try:
                    msg = json.loads(data)
                    msg_type = msg.get('type')
                    
                    if msg_type == 'STREAM_REQUEST':
                        stream_id = msg.get('stream_id')
                        requester = msg.get('requester_id')
                        print(f"[{self.node_id}] Stream '{stream_id}' requested by {requester}")
                        # TODO: Handle stream request - start sending video data
                        
                    elif msg_type == 'STREAM_DATA':
                        # Handle incoming stream data
                        print(f"[{self.node_id}] Received stream data")
                        # TODO: Process video stream data
                        
                except json.JSONDecodeError:
                    print(f"[{self.node_id}] Invalid JSON in stream message")
                    
        except Exception as e:
            print(f"[{self.node_id}] Error handling stream: {e}")
        finally:
            conn.close()

    def handle_alive_connection(self, conn, addr):
        """
        Handles incoming alive/heartbeat messages.
        """
        try:
            data = conn.recv(1024).decode()
            if data:
                try:
                    msg = json.loads(data)
                    if msg.get('type') == 'ALIVE':
                        sender_id = msg.get('node_id')
                        timestamp = msg.get('timestamp')
                        print(f"[{self.node_id}] ALIVE from {sender_id} at {timestamp}")
                        # TODO: Update node liveness tracking
                        
                        # Send acknowledgment
                        response = json.dumps({
                            'type': 'ALIVE_ACK',
                            'node_id': self.node_id,
                            'timestamp': int(time.time())
                        })
                        conn.send(response.encode())
                        
                except json.JSONDecodeError:
                    print(f"[{self.node_id}] Invalid JSON in alive message")
                    
        except Exception as e:
            print(f"[{self.node_id}] Error handling alive: {e}")
        finally:
            conn.close()

    def start_all_listeners(self):
        """
        Starts all listeners (flood, stream, alive) in separate background threads.
        """
        # Start flood listener
        flood_thread = threading.Thread(target=self.start_flood_listener, daemon=True)
        flood_thread.start()
        
        # Start stream listener
        stream_thread = threading.Thread(target=self.start_stream_listener, daemon=True)
        stream_thread.start()
        
        # Start alive listener
        alive_thread = threading.Thread(target=self.start_alive_listener, daemon=True)
        alive_thread.start()
        
        print(f"[{self.node_id}] All listeners started")
        print(f"  - Flood port: {self.flood_port}")
        print(f"  - Stream port: {self.stream_port}")
        print(f"  - Alive port: {self.alive_port}")

   
