import sys
import os
import socket
import json
import threading
import time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class Node:
    
    def __init__(self, node_id, node_ip, bootstrapper_ip, bootstrapper_port, 
                 flood_port=6000, stream_port=1000, alive_port=2000):
        self.node_id = node_id
        self.node_ip = node_ip
        
        # Define ports for different message types
        self.flood_port = flood_port      # Port for flood messages (routing table construction)
        self.stream_port = stream_port    # Port for video streaming
        self.alive_port = alive_port      # Port for alive/heartbeat messages
        
        self.neighbors = self.register_with_bootstrapper(node_ip, bootstrapper_ip, bootstrapper_port)
        self.routing_table = {}  # {destination_id: next_hop_ip}
        self.flood_cache = set()  # Track seen flood messages to avoid loops
        self.lock = threading.Lock()  # For thread-safe operations
        
        
    def register_with_bootstrapper(self, node_ip, bootstrapper_ip, bootstrapper_port):
        """ Registers the node with the bootstrapper and retrieves neighbors."""
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect((bootstrapper_ip, bootstrapper_port))
        print(f"[CTRL] Connected to Bootstrapper at {bootstrapper_ip}:{bootstrapper_port}")

        # Envia o registo
        message = f"REGISTER {node_ip}"
        client.send(message.encode())

        # Recebe resposta
        response = client.recv(4096).decode()
        client.close()

        return response
    
    
    
    
    
    def handle_flood_message(self, flood_msg, sender_ip):
        """
        Handles incoming flood message to build routing table.
        
        Args:
            flood_msg: dict with 'flood_id', 'origin_id', 'origin_ip', 'hop_count'
            sender_ip: IP of the node that sent this message
        """
        flood_id = flood_msg.get('flood_id')
        origin_id = flood_msg.get('origin_id')
        origin_ip = flood_msg.get('origin_ip')
        hop_count = flood_msg.get('hop_count', 0)
        
        # Check if we've already processed this flood message
        with self.lock:
            if flood_id in self.flood_cache:
                print(f"[{self.node_id}] Ignoring duplicate flood {flood_id}")
                return False
            
            # Mark this flood as seen
            self.flood_cache.add(flood_id)
            
            # Update routing table: to reach origin, go through sender
            if origin_id not in self.routing_table:
                self.routing_table[origin_id] = {
                    'next_hop': sender_ip,
                    'hop_count': hop_count
                }
                print(f"[{self.node_id}] Added route to {origin_id} via {sender_ip} (hops: {hop_count})")
            elif self.routing_table[origin_id]['hop_count'] > hop_count:
                # Found a shorter path
                self.routing_table[origin_id] = {
                    'next_hop': sender_ip,
                    'hop_count': hop_count
                }
                print(f"[{self.node_id}] Updated route to {origin_id} via {sender_ip} (hops: {hop_count})")
        
        return True
    
    def forward_flood_message(self, flood_msg, exclude_ip=None):
        """
        Forwards flood message to all neighbors except the sender.
        
        Args:
            flood_msg: dict with flood message data
            exclude_ip: IP to exclude from forwarding (typically the sender)
        """
        # Increment hop count for forwarding
        new_flood_msg = flood_msg.copy()
        new_flood_msg['hop_count'] = flood_msg.get('hop_count', 0) + 1
        
        # Parse neighbors (assuming it's a string representation of neighbors)
        # You may need to adjust this based on your actual neighbor format
        neighbor_list = self._parse_neighbors(self.neighbors)
        
        for neighbor_ip in neighbor_list:
            if neighbor_ip == exclude_ip:
                continue
            
            try:
                self._send_flood_to_neighbor(neighbor_ip, new_flood_msg)
                print(f"[{self.node_id}] Forwarded flood {flood_msg['flood_id']} to {neighbor_ip}")
            except Exception as e:
                print(f"[{self.node_id}] Failed to forward flood to {neighbor_ip}: {e}")
                
                
    
    def _send_flood_to_neighbor(self, neighbor_ip, flood_msg):
        """
        Sends flood message to a specific neighbor.
        
        Args:
            neighbor_ip: IP address of the neighbor
            flood_msg: dict with flood message data
        """
        # Use the flood port for flood messages
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(5)
        try:
            client.connect((neighbor_ip, self.flood_port))
            message = json.dumps({'type': 'FLOOD', 'data': flood_msg})
            client.send(message.encode())
        finally:
            client.close()
    
    def _parse_neighbors(self, neighbors_data):
        """
        Parses neighbor data into a list of IPs.
        Adjust this based on your actual neighbor format.
        """
        # This is a placeholder - adjust based on your actual format
        if isinstance(neighbors_data, str):
            try:
                # Try to parse as JSON
                neighbor_list = json.loads(neighbors_data)
                if isinstance(neighbor_list, list):
                    return neighbor_list
            except:
                pass
        elif isinstance(neighbors_data, list):
            return neighbors_data
        
        return []
    
    def print_routing_table(self):
        """Prints the current routing table."""
        print(f"\n[{self.node_id}] Routing Table:")
        if not self.routing_table:
            print("  (empty)")
        else:
            for dest, route_info in self.routing_table.items():
                print(f"  {dest} -> via {route_info['next_hop']} (hops: {route_info['hop_count']})")
        print()
    
    def send_alive_message(self, target_ip):
        """
        Sends an alive/heartbeat message to a target node.
        
        Args:
            target_ip: IP address of the target node
        """
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(5)
        try:
            client.connect((target_ip, self.alive_port))
            message = json.dumps({
                'type': 'ALIVE',
                'node_id': self.node_id,
                'node_ip': self.node_ip,
                'timestamp': int(time.time())
            })
            client.send(message.encode())
            print(f"[{self.node_id}] Sent ALIVE to {target_ip}:{self.alive_port}")
        except Exception as e:
            print(f"[{self.node_id}] Failed to send ALIVE to {target_ip}: {e}")
        finally:
            client.close()
    
    def request_stream(self, target_ip, stream_id):
        """
        Requests a video stream from a target node.
        
        Args:
            target_ip: IP address of the node hosting the stream
            stream_id: Identifier of the requested stream
        """
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(5)
        try:
            client.connect((target_ip, self.stream_port))
            message = json.dumps({
                'type': 'STREAM_REQUEST',
                'requester_id': self.node_id,
                'requester_ip': self.node_ip,
                'stream_id': stream_id
            })
            client.send(message.encode())
            print(f"[{self.node_id}] Requested stream '{stream_id}' from {target_ip}:{self.stream_port}")
        except Exception as e:
            print(f"[{self.node_id}] Failed to request stream from {target_ip}: {e}")
        finally:
            client.close()
    
    def alive(self):
        
    
    
        
    
    


