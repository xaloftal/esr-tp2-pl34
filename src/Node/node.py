import sys
import os
import socket
import json
import threading
import time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Proto.aux_message import MessageType, create_message, parse_message, get_message_type


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
    #   NODE METHODS
    #
    
    def join_overlay(self):
        """Starts the node's main functionalities."""
        threading.Thread(target=self.start_tcp_listener, daemon=True).start()
        # Additional listeners (UDP, etc.) can be started here as needed.
        
        # tell neighbors we're joining
        
        
        print(f"[{self.node_id}] Joined overlay network.")
        
    
    def leave_overlay(self):
        """Cleans up before leaving the overlay network."""
        print(f"[{self.node_id}] Leaving overlay network.")
        # Notify neighbors.
        # Close sockets and clean up resources.
    
    
    
    #
    #   MESSAGE LISTENERS
    #
    
    # for all control messages
    def start_tcp_listener(self):
        """Start a listener for incoming messages on TCP port."""
        
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.node_ip, self.tcpport))        
        
        print(f"[{self.node_id}] TCP listener on {self.node_ip}:{self.tcpport}")

        while True:
            conn, addr = server.accept()
            threading.Thread(target=self.handle_tcp_message, args=(conn, addr), daemon=True).start()
            
            
    # for the streaming datagrams    
    def start_udp_listener(self):
        """Start a listener for incoming messages on UDP port."""
        
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.bind((self.node_ip, self.udpport))        
        
        print(f"[{self.node_id}] UDP listener on {self.node_ip}:{self.udpport}")

        while True:
            data, addr = server.recvfrom(4096)
            threading.Thread(target=self.handle_udp_message, args=(data, addr), daemon=True).start()    
            
            
    #       
    #  MESSAGE HANDLERS
    #
      
    def handle_tcp_message(self, conn, addr):
        """Handles incoming TCP messages."""
        try:
            data = conn.recv(1024).decode()
            
            if data:
                print(f"[{self.node_id}] TCP received from {addr}: {data}")
                
                msg = parse_message(data)
                if not msg:
                    print(f"[{self.node_id}] Failed to parse message")
                    return
                
                msg_type = get_message_type(msg)
                
                # route to appropriate handler based on message type                
                match(msg_type):
                    case MessageType.FLOOD.value:
                        self.handle_flood_message(msg.get('data'), addr[0])
                    case MessageType.ALIVE.value:
                        self.handle_alive_message(msg.get('data'), addr[0])
                    case MessageType.JOIN.value:
                        self.handle_join_message(msg.get('data'), addr[0])
                    case MessageType.LEAVE.value:
                        self.handle_leave_message(msg.get('data'), addr[0])
                    case MessageType.STREAM_START.value:
                        self.handle_stream_start_message(msg.get('data'), addr[0])
                    case MessageType.STREAM_END.value:
                        self.handle_stream_end_message(msg.get('data'), addr[0])
                    case _:
                        print(f"[{self.node_id}] Unknown message type: {msg_type}")    
           else:
                print(f"[{self.node_id}] Empty TCP message from {addr}")          

        except Exception as e:
            print(f"[{self.node_id}] TCP error receiving: {e}")
        finally:
            conn.close()
            
            
    
    def handle_udp_message(self, data, addr):
        """Handles incoming UDP messages."""
        try:
            print(f"[{self.node_id}] UDP received from {addr}")
            
            # Parse message
            msg = parse_message(data)
            if not msg:
                print(f"[{self.node_id}] Failed to parse UDP message")
                return
            
            # Get message type
            msg_type = get_message_type(msg)
            
            # Route to appropriate handler
            if msg_type == MessageType.STREAM_DATA.value:
                self.handle_stream_data_message(msg.get('data'), addr[0])
            else:
                print(f"[{self.node_id}] Unknown UDP message type: {msg_type}")
                
        except Exception as e:
            print(f"[{self.node_id}] UDP error receiving: {e}")
            
            
    
    #
    # MESSAGE TYPE HANDLERS
    #
    
    def handle_flood_message(self, data, sender_ip):
        """Handle FLOOD message for routing table construction."""
        print(f"[{self.node_id}] Handling FLOOD from {sender_ip}")
        # TODO: Implement flood handling logic
        pass
    
    def handle_alive_message(self, data, sender_ip):
        """Handle ALIVE heartbeat message."""
        print(f"[{self.node_id}] Handling ALIVE from {sender_ip}")
        # TODO: Implement alive handling logic
        pass
    
    def handle_join_message(self, data, sender_ip):
        """Handle JOIN overlay message."""
        print(f"[{self.node_id}] Handling JOIN from {sender_ip}")
        # TODO: Implement join handling logic
        pass
    
    def handle_leave_message(self, data, sender_ip):
        """Handle LEAVE overlay message."""
        print(f"[{self.node_id}] Handling LEAVE from {sender_ip}")
        # TODO: Implement leave handling logic
        pass
    
    def handle_stream_start_message(self, data, sender_ip):
        """Handle STREAM_START request."""
        print(f"[{self.node_id}] Handling STREAM_START from {sender_ip}")
        # TODO: Implement stream start logic
        pass
    
    def handle_stream_end_message(self, data, sender_ip):
        """Handle STREAM_END notification."""
        print(f"[{self.node_id}] Handling STREAM_END from {sender_ip}")
        # TODO: Implement stream end logic
        pass
    
    def handle_stream_data_message(self, data, sender_ip):
        """Handle STREAM_DATA (video chunks)."""
        print(f"[{self.node_id}] Handling STREAM_DATA from {sender_ip}")
        # TODO: Implement stream data handling logic
        pass
            
    
    
    # TODO: have a way to keep track of the neighbours that are active
    
    
        