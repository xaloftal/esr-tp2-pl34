import socket
import threading
import json
import time
import uuid
import numpy as np
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Node.node import Node
import Bootstrapper.overlay_nodes as nodes

class Server(Node):
  
  def __init__(self, node_id, node_ip, bootstrapper_ip, bootstrapper_port,
               flood_port=6000, stream_port=1000, alive_port=2000):
      super().__init__(node_id, node_ip, bootstrapper_ip, bootstrapper_port,
                      flood_port, stream_port, alive_port) 


  def start(self):
      server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
      server.bind((self.node_ip, self.control_port))
      server.listen()
      print(f"[{self.node_id}] listening on {self.node_ip}:{self.control_port}")

      while True:
          conn, addr = server.accept()
          threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()

  def handle_client(self, conn, addr):
        try:
            data = conn.recv(1024).decode()
            if data:
                print(f"[{self.node_id}] recebeu de {addr}: {data}")
                
                # Try to parse as JSON message
                try:
                    msg = json.loads(data)
                    if msg.get('type') == 'FLOOD':
                        # This is a flood message coming back (shouldn't happen for server)
                        print(f"[{self.node_id}] Received flood message (unexpected for server)")
                except json.JSONDecodeError:
                    # Not a JSON message, handle as plain text
                    pass
                    
        except Exception as e:
            print(f"[{self.node_id}] erro a receber: {e}")
        finally:
            conn.close()
    
    def initiate_flood(self):
        """
        Initiates a flood message to build routing tables across the network.
        This should be called by the server when it wants nodes to update their routes.
        """
        flood_id = str(uuid.uuid4())  # Unique ID for this flood
        flood_msg = {
            'flood_id': flood_id,
            'origin_id': self.node_id,
            'origin_ip': self.node_ip,
            'hop_count': 1  # Starting at 1 for first hop
        }
        
        print(f"[{self.node_id}] Initiating flood with ID: {flood_id}")
        
        # Add to our own flood cache to avoid processing it if it comes back
        with self.lock:
            self.flood_cache.add(flood_id)
        
        # Send to all neighbors
        self.forward_flood_message(flood_msg, exclude_ip=None)
        
        print(f"[{self.node_id}] Flood initiated and sent to neighbors")
    
    def manual_flood(self):
        """
        Manually trigger a flood message.
        Can be called from CLI or other interface.
        """
        print(f"\n[{self.node_id}] === Manual Flood Triggered ===")
        self.initiate_flood()
    

    
    