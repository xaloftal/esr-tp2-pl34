# Ficheiro: src/Node/control_client.py
import socket
import json
import time
from config import BOOTSTRAPPER_IP, BOOTSTRAPPER_PORT, NODE_TCP_PORT

class ControlClient():
    """ lado "cliente" do nó P2P: vai receber a stream de video via UDP. """
    
    def __init__(self, node_id, node_ip, bootstrapper_ip, bootstrapper_port, is_server=False):
        self.node_id = node_id
        self.node_ip = node_ip
        self.TCPport = NODE_TCP_PORT
        self.UDPport = NODE_UDP_PORT
        

    