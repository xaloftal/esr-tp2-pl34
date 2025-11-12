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
from Proto.aux_message import MessageType, create_message, parse_message, get_message_type


class Server(Node):
  
  def __init__(self, node_id, node_ip, bootstrapper_ip,bootstrapper_port = 1000, tcpport = 6000, udpport = 7000, videosrc):
      super().__init__(node_id, node_ip, bootstrapper_ip, bootstrapper_port, tcpport, udpport) 
      self.videosrc = videosrc


    #
    # FLOOD METHODS
    # 
    
    def initiate_flood(self):
        """
        Initiates a flood message to build routing tables across the network.
        This should be called by the server when it wants nodes to update their routes.
        """
        flood_id = str(uuid.uuid4())  # Unique ID for this flood
        print(f"[{self.node_id}] Initiating flood with ID: {flood_id}")

        for neighbor_ip in self.neighbors:      
            msg = create_message(msg_id = flood_id, 
                                msg_type = MessageType.FLOOD,
                                srcip = self.node_ip,
                                destip = neighbor_ip,
                                data={
                                    # TODO: change this into a metric, like bamdwidth
                                    'hop_count': 0
                                })
            self.forward_flood_message(msg)
        
        # Add to our own flood cache to avoid processing it if it comes back
        with self.lock:
            self.flood_cache.add(flood_id)       
        
        print(f"[{self.node_id}] Flood initiated and sent to neighbors")
    
    
    
    #
    # DEPLOYABLE METHODS
    #
    def manual_flood(self):
        """
        Manually trigger a flood message.
        """
        print(f"\n[{self.node_id}] === Manual Flood Triggered ===")
        self.initiate_flood()
    

    #
    # AUXILIARY METHODS
    #
    
    def forward_flood_message(self, msg):
        """
        Forwards a flood message to a neighbor.
        """
        dest_ip = msg['destip']
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((dest_ip, self.tcpport))
            sock.send(json.dumps(msg).encode())
            sock.close()
            print(f"[{self.node_id}] Forwarded FLOOD to {dest_ip}")
        except Exception as e:
            print(f"[{self.node_id}] Error forwarding FLOOD to {dest_ip}: {e}")
    
    