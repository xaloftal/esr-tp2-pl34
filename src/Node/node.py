import sys
import os
import socket
import json
import threading
import time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class Node:
    
    def __init__(self, node_id, node_ip, bootstrapper_ip, bootstrapper_port = 1000, tcpport = 6000, udpport = 7000):
        self.node_id = node_id
        self.node_ip = node_ip        
        self.tcpport = tcpport
        self.udpport = udpport

        self.neighbors = self.register_with_bootstrapper(node_ip, bootstrapper_ip, bootstrapper_port)
        self.routing_table = {}  # {destination_id: next_hop_ip}
        self.flood_cache = set()  # Track seen flood messages to avoid loops
        self.lock = threading.Lock()  # For thread-safe operations
        
    #
    #   REGISTRY
    #
    def register_with_bootstrapper(self, node_ip, bootstrapper_ip, bootstrapper_port):
        """ Registers the node with the bootstrapper and retrieves neighbors."""
        
        # TCP socket to communicate with Bootstrapper
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect((bootstrapper_ip, bootstrapper_port))        
        
        print(f"[CTRL] Connected to Bootstrapper at {bootstrapper_ip}:{bootstrapper_port}")

        message = f"REGISTER {node_ip}"
        client.send(message.encode())
        
        # Receive response
        response = client.recv(4096).decode()
        client.close()

        return response
    
    
    
    #
    #   MESSAGE HANDLER
    #
    def start_listener(self):
        
        pass
        # have here a listener that will handle different types of messages
        