# node.py
import sys
import os
import socket
import json
import threading
import time
from enum import Enum
import uuid


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Proto import control_proto_pb2 as control_proto

class MessageType(Enum):
    FLOOD = "FLOOD"
    ALIVE = "ALIVE"
    JOIN = "JOIN"
    LEAVE = "LEAVE"
    STREAM_START = "STREAM_START"
    STREAM_END = "STREAM_END"
    STREAM_DATA = "STREAM_DATA"


def parse_message(raw):
    """Converte bytes/string JSON -> dict Python."""
    if isinstance(raw, bytes):
        raw = raw.decode(errors="ignore")
    try:
        return json.loads(raw)
    except Exception:
        return None


def get_message_type(msg: dict):
    """Lê o campo msg_type da mensagem."""
    return msg.get("msg_type")


class Node:
    def __init__(self, node_id, node_ip, bootstrapper_ip,
                 bootstrapper_port=5000, tcpport=6000, udpport=7000):
        self.node_id = node_id
        self.node_ip = node_ip
        self.tcpport = tcpport          # Porta única para controlo (FLOOD, ALIVE, STREAM_START, etc.)
        self.udpport = udpport          # Porta única para streaming (UDP)
        self.neighbors = self.register_with_bootstrapper(
            node_ip, bootstrapper_ip, bootstrapper_port
        )  # lista de IPs vizinhos

        self.routing_table = {}         # {destination_ip: next_hop_ip}
        self.flood_cache = set()        # IDs de floods já vistos
        self.lock = threading.Lock()
        self.last_alive = {}            # {ip: timestamp}

    # ------------------------------------------------------------------
    #   REGISTO NO BOOTSTRAPPER
    # ------------------------------------------------------------------
    def register_with_bootstrapper(self, node_ip, bootstrapper_ip, bootstrapper_port):
        """Regista o node no bootstrapper e obtém lista de vizinhos."""
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect((bootstrapper_ip, bootstrapper_port))
        print(f"[CTRL] Connected to Bootstrapper at {bootstrapper_ip}:{bootstrapper_port}")

        message = f"REGISTER {node_ip}\n"
        client.sendall(message.encode())

        response = client.recv(4096).decode()
        client.close()

        try:
            data = json.loads(response)
            neighbors = data.get("neighbors", [])
            print(f"[{self.node_id}] Neighbors from bootstrapper: {neighbors}")
            return neighbors
        except json.JSONDecodeError:
            print(f"[{self.node_id}] Failed to parse bootstrapper response: {response}")
            return []

    # ------------------------------------------------------------------
    #   JOIN / LEAVE
    # ------------------------------------------------------------------
    def join_overlay(self):
        """Inicia listeners TCP e UDP."""
        threading.Thread(target=self.start_tcp_listener, daemon=True).start()
        threading.Thread(target=self.start_udp_listener, daemon=True).start()
        print(f"[{self.node_id}] Joined overlay network.")

    def leave_overlay(self):
        """Placeholder para lógica de saída."""
        print(f"[{self.node_id}] Leaving overlay network.")
        # Aqui poderias enviar uma mensagem LEAVE, etc.

    # ------------------------------------------------------------------
    #   LISTENERS
    # ------------------------------------------------------------------
    def start_tcp_listener(self):
        """Listener para mensagens de controlo via TCP."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.node_ip, self.tcpport))
        server.listen()
        print(f"[{self.node_id}] TCP listener on {self.node_ip}:{self.tcpport}")

        while True:
            conn, addr = server.accept()
            threading.Thread(target=self.handle_tcp_message, args=(conn, addr), daemon=True).start()

    def start_udp_listener(self):
        """Listener para dados de stream via UDP."""
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.bind((self.node_ip, self.udpport))
        print(f"[{self.node_id}] UDP listener on {self.node_ip}:{self.udpport}")

        while True:
            data, addr = server.recvfrom(65535)
            threading.Thread(target=self.handle_udp_message, args=(data, addr), daemon=True).start()

    # ------------------------------------------------------------------
    #   ENVIO DE MENSAGENS
    # ------------------------------------------------------------------
    def send_tcp_message(self, dest_ip, msg_dict):
        """Envia mensagem de controlo via TCP para dest_ip."""
        try:
            payload = json.dumps(msg_dict).encode()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((dest_ip, self.tcpport))
                sock.sendall(payload)
            print(f"[{self.node_id}] TCP sent to {dest_ip}: {msg_dict.get('msg_type')}")
        except Exception as e:
            print(f"[{self.node_id}] Error sending TCP to {dest_ip}: {e}")

    def send_udp_message(self, dest_ip, data_bytes):
        """Envia dados via UDP (por exemplo, chunks de vídeo)."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.sendto(data_bytes, (dest_ip, self.udpport))
        except Exception as e:
            print(f"[{self.node_id}] Error sending UDP to {dest_ip}: {e}")

    # ------------------------------------------------------------------
    #   HANDLER TCP
    # ------------------------------------------------------------------
    def handle_tcp_message(self, conn, addr):
        """Recebe e despacha mensagens TCP de controlo."""
        try:
            raw = conn.recv(65535)
            if not raw:
                print(f"[{self.node_id}] Empty TCP message from {addr}")
                return

            data = raw.decode()
            print(f"[{self.node_id}] TCP received from {addr}: {data}")

            msg = parse_message(data)
            if not msg:
                print(f"[{self.node_id}] Failed to parse message")
                return

            msg_type = get_message_type(msg)

            # Despacho por tipo de mensagem
            match msg_type:
                case MessageType.FLOOD.value:
                    self.handle_flood_message(msg, addr[0])
                case MessageType.ALIVE.value:
                    self.handle_alive_message(msg, addr[0])
                case MessageType.JOIN.value:
                    self.handle_join_message(msg, addr[0])
                case MessageType.LEAVE.value:
                    self.handle_leave_message(msg, addr[0])
                case MessageType.STREAM_START.value:
                    self.handle_stream_start_message(msg, addr[0])
                case MessageType.STREAM_END.value:
                    self.handle_stream_end_message(msg, addr[0])
                case _:
                    print(f"[{self.node_id}] Unknown message type: {msg_type}")

        except Exception as e:
            print(f"[{self.node_id}] TCP error receiving: {e}")
        finally:
            conn.close()

    # ------------------------------------------------------------------
    #   HANDLER UDP
    # ------------------------------------------------------------------
    def handle_udp_message(self, data, addr):
        """Recebe e encaminha STREAM_DATA via UDP."""
        try:
            try:
                text = data.decode("utf-8")
            except:
                print(f"[{self.node_id}] UDP decode error")
                return

            msg = parse_message(text)
            if not msg:
                print(f"[{self.node_id}] Invalid UDP message")
                return

            msg_type = get_message_type(msg)
            dest = msg.get("destip")

            # ===========================================================
            # 1) MENSAGEM TEST (possui apenas "text")
            # ===========================================================
            if msg_type == MessageType.STREAM_DATA.value and "text" in msg["data"]:

                # É para mim? → mostrar
                if dest == self.node_ip:
                    print(f"[{self.node_id}] TEST message received: {msg['data']['text']}")
                    return

                # NÃO é para mim → reencaminhar
                next_hop = self.routing_table.get(dest)
                if not next_hop:
                    print(f"[{self.node_id}] No route to {dest}")
                    return

                print(f"[{self.node_id}] Forwarding TEST to {dest} via {next_hop}")
                self.send_udp_message(next_hop, data)
                return


            # ===========================================================
            # 2) STREAM_DATA NORMAL
            # ===========================================================
            if msg_type != MessageType.STREAM_DATA.value:
                print(f"[{self.node_id}] Unknown UDP msg_type: {msg_type}")
                return

            # NÃO SOU O DESTINO → encaminhar
            if dest != self.node_ip:
                next_hop = self.routing_table.get(dest)
                if not next_hop:
                    print(f"[{self.node_id}] No route to {dest}")
                    return
                print(f"[{self.node_id}] Forwarding STREAM_DATA to {dest} via {next_hop}")
                self.send_udp_message(next_hop, data)
                return

            # SOU O DESTINO
            print(f"[{self.node_id}] Received STREAM_DATA: {msg}")

        except Exception as e:
            print(f"[{self.node_id}] UDP error receiving: {e}")



    # ------------------------------------------------------------------
    #   HANDLERS DE TIPOS DE MENSAGEM
    # ------------------------------------------------------------------
    def handle_flood_message(self, msg, sender_ip):
        """Constrói routing_table com base no FLOOD."""
        msg_id = msg.get("msg_id")
        data = msg.get("data", {})
        src_ip = msg.get("srcip")
        hop_count = data.get("hop_count", 0)

        print(f"[{self.node_id}] Handling FLOOD from {sender_ip}, src={src_ip}, id={msg_id}")

        # ---- flood_cache com (msg_id, src_ip) ----
        key = (msg_id, src_ip)

        with self.lock:
            if not hasattr(self, "flood_cache"):
                self.flood_cache = set()

            if key in self.flood_cache:
                print(f"[{self.node_id}] FLOOD {key} already seen, ignoring.")
                return

            self.flood_cache.add(key)

            # Rota para a origem (src_ip) passa pelo sender_ip
            if src_ip is not None and src_ip != self.node_ip:
                self.routing_table[src_ip] = sender_ip
                print(f"[{self.node_id}] Routing updated: {src_ip} -> {sender_ip}")

        # Incrementar hop_count
        data["hop_count"] = hop_count + 1
        msg["data"] = data


        # Encaminhar para outros vizinhos (menos o sender)
        for neighbor_ip in self.neighbors:
            if neighbor_ip == sender_ip:
                continue

            forward_msg = msg.copy()
            forward_msg["destip"] = neighbor_ip
            self.send_tcp_message(neighbor_ip, forward_msg)



    def handle_alive_message(self, msg, sender_ip):
        """Regista heartbeat do vizinho."""
        timestamp = msg.get("data", {}).get("timestamp", time.time())
        self.last_alive[sender_ip] = timestamp
        print(f"[{self.node_id}] ALIVE from {sender_ip} at {timestamp}")

    def handle_join_message(self, msg, sender_ip):
        print(f"[{self.node_id}] Handling JOIN from {sender_ip}")
        # Se quiseres, podes adicionar o sender à tabela de vizinhos ou afins

    def handle_leave_message(self, msg, sender_ip):
        print(f"[{self.node_id}] Handling LEAVE from {sender_ip}")
        # Remover rotas ou marcar como inativo

    def handle_stream_start_message(self, msg, sender_ip):
        print(f"[{self.node_id}] Handling STREAM_START from {sender_ip}, data={msg.get('data')}")

    def handle_stream_end_message(self, msg, sender_ip):
        print(f"[{self.node_id}] Handling STREAM_END from {sender_ip}")

    def send_test_message(self, dest_ip, text="test"):
        msg = {
            "msg_type": MessageType.STREAM_DATA.value,
            "msg_id": str(uuid.uuid4()),
            "srcip": self.node_ip,
            "destip": dest_ip,
            "data": {
                "text": text
            }
        }

        # Descobrir próximo salto
        next_hop = self.routing_table.get(dest_ip)
        if not next_hop:
            print(f"[{self.node_id}] No route to {dest_ip}")
            return

        print(f"[{self.node_id}] Sending TEST STREAM_DATA to {dest_ip} via {next_hop}")
        self.send_udp_message(next_hop, json.dumps(msg).encode())


    def start_flood(self):
        flood_id = str(uuid.uuid4())
        msg = {
            "msg_type": MessageType.FLOOD.value,
            "msg_id": flood_id,
            "srcip": self.node_ip,
            "destip": None,
            "data": {"hop_count": 0},
        }

        print(f"[{self.node_id}] Starting FLOOD id={flood_id}")

        # NÃO adicionar flood_id à flood_cache aqui!

        for neigh_ip in self.neighbors:
            msg_to_send = msg.copy()
            msg_to_send["destip"] = neigh_ip
            self.send_tcp_message(neigh_ip, msg_to_send)


        # ------------------------------------------------------------------
    #   STREAMING (SINALIZAÇÃO)
    # ------------------------------------------------------------------
    def start_stream(self, dest_ip, stream_id="default"):
        """Envia STREAM_START para um destino (podes depois usar routing_table)."""
        msg = {
            "msg_type": MessageType.STREAM_START.value,
            "msg_id": str(uuid.uuid4()),
            "srcip": self.node_ip,
            "destip": dest_ip,
            "data": {
                "stream_id": stream_id,
            },
        }

        # Por agora, envia diretamente para dest_ip (depois podemos usar uma routing_table)
        self.send_tcp_message(dest_ip, msg)
        print(f"[{self.node_id}] STREAM_START -> {dest_ip} (stream_id={stream_id})")

    def stream_file(self, filename, dest_ip):
        """Envia um ficheiro em chunks UDP multi-hop (com índice e EOF)."""

        if not os.path.exists(filename):
            print(f"[{self.node_id}] Ficheiro não encontrado: {filename}")
            return

        print(f"[{self.node_id}] A enviar ficheiro '{filename}' para {dest_ip}")

        # STREAM_START primeiro
        self.start_stream(dest_ip, stream_id=filename)

        time.sleep(0.2)

        try:
            index = 0  # índice dos chunks

            with open(filename, "rb") as f:
                while True:
                    chunk = f.read(1300)
                    if not chunk:
                        break

                    msg = {
                        "msg_type": MessageType.STREAM_DATA.value,
                        "msg_id": str(uuid.uuid4()),
                        "srcip": self.node_ip,
                        "destip": dest_ip,
                        "data": {
                            "filename": filename,
                            "chunk": chunk.hex(),
                            "index": index
                        }
                    }

                    next_hop = self.routing_table.get(dest_ip)
                    if not next_hop:
                        print(f"[{self.node_id}] Sem rota para {dest_ip}")
                        return

                    self.send_udp_message(next_hop, json.dumps(msg).encode())
                    index += 1
                    time.sleep(0.01)

            # -------------------------------
            # ENVIAR MENSAGEM FINAL (EOF)
            # -------------------------------
            msg_end = {
                "msg_type": MessageType.STREAM_DATA.value,
                "msg_id": str(uuid.uuid4()),
                "srcip": self.node_id,
                "destip": dest_ip,
                "data": {
                    "filename": filename,
                    "eof": True,
                    "total_chunks": index
                }
            }

            next_hop = self.routing_table.get(dest_ip)
            self.send_udp_message(next_hop, json.dumps(msg_end).encode())

            print(f"[{self.node_id}] Ficheiro '{filename}' enviado com sucesso (EOF enviado).")

        except Exception as e:
            print(f"[{self.node_id}] Erro ao enviar ficheiro: {e}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Uso: python3 node.py NODE_ID NODE_IP BOOTSTRAPPER_IP")
        sys.exit(1)

    node_id = sys.argv[1]
    node_ip = sys.argv[2]
    bootstrap_ip = sys.argv[3]

    # Cria nó e regista no bootstrapper
    node = Node(
        node_id=node_id,
        node_ip=node_ip,
        bootstrapper_ip=bootstrap_ip,
        bootstrapper_port=5000,  # porta do teu bootstrapper
        tcpport=6000,
        udpport=7000,
    )

    # Inicia listeners TCP/UDP
    node.join_overlay()

    # Pequena pausa para ter a certeza que os listeners arrancam
    time.sleep(0.5)

    # Loop de comandos interativos
    while True:
        cmd = input(f"[{node_id}] Comando (flood/stream/routes/neigh/test/exit): ").strip().lower()

        if cmd == "flood":
            node.start_flood()

        elif cmd.startswith("stream"):
            parts = cmd.split()
            
            # Caso 1: stream <dest_ip>  → apenas STREAM_START
            if len(parts) == 2:
                dest = parts[1]
                node.start_stream(dest)

            # Caso 2: stream <ficheiro> <dest_ip>  → envia vídeo ou ficheiro
            elif len(parts) == 3:
                filename = parts[1]
                dest = parts[2]
                node.stream_file(filename, dest)

            else:
                print("Uso: stream <dest_ip>  ou  stream <ficheiro> <dest_ip>")



        elif cmd == "routes":
            print(f"[{node_id}] routing_table = {node.routing_table}")

        elif cmd == "neigh":
            print(f"[{node_id}] neighbors = {node.neighbors}")
        
        elif cmd.startswith("test"):
            parts = cmd.split()
            if len(parts) == 2:
                dest = parts[1]
                node.send_test_message(dest, text="HELLO FROM " + node.node_id)
            else:
                print("Uso: test <dest_ip>")
        
        elif cmd == "exit":
            print(f"[{node_id}] Exiting...")
            node.leave_overlay()
            break

        else:
            print("Comandos: flood | stream <dest_ip> | routes | neigh | exit")
