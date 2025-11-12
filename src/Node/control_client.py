# control_client.py
import sys
import os
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Node.node import Node
from Proto.aux_message import MessageType, create_message


class Client(Node):
    """Cliente que consome streams e participa no overlay."""

    def __init__(self, node_id, node_ip, bootstrapper_ip,
                 bootstrapper_port=1000, tcpport=6000, udpport=7000):
        super().__init__(node_id, node_ip, bootstrapper_ip, bootstrapper_port,
                         tcpport, udpport)

    # -------------------------------------------------------------
    # PEDIR STREAM
    # -------------------------------------------------------------
    def request_stream(self, server_ip, stream_id="default"):
        """Envia um pedido STREAM_START ao servidor."""
        msg = create_message(
            msg_id=str(uuid.uuid4()),
            msg_type=MessageType.STREAM_START,
            srcip=self.node_ip,
            destip=server_ip,
            data={"stream_id": stream_id, "requester_id": self.node_id}
        )
        self.send_tcp_message(server_ip, msg)
        print(f"[{self.node_id}] Requested stream '{stream_id}' from {server_ip}")

