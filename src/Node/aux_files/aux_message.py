from enum import Enum
import uuid
import json
import time


class MsgType:
    """Message type constants"""
    
    # Control messages (TCP)
    FLOOD = "FLOOD"
    ALIVE = "ALIVE"
    JOIN = "JOIN"
    LEAVE = "LEAVE"
    STREAM_START = "STREAM_START"
    STREAM_END = "STREAM_END"
    REGISTER = "REGISTER"
    NEIGHBOUR = "NEIGHBOUR"
    
    # Data messages (UDP)
    STREAM_DATA = "STREAM_DATA"
    
    # Acknowledgments
    ALIVE_ACK = "ALIVE_ACK"


class Message:
    """
    Classe mensagem para comunicação entre nós.
    
    Estrutura da mensagem:
    {
        "id": id unico,
        "type": tipo da mensagem (de MsgType),
        "srcip": endereço IP de origem,
        "destip": endereço IP de destino (ou "broadcast"),
        "timestamp": quando a mensagem foi criada,
        "payload": dados específicos da mensagem
    }
    """
    
    def __init__(self, msg_type, srcip, destip="broadcast", payload=None, msg_id=None):
        """
        Cria uma nova mensagem.
        
        Args:
            msg_type: Tipo da mensagem (usar constantes de MsgType)
            srcip: Endereço IP de origem
            destip: Endereço IP de destino (padrão: "broadcast")
            payload: Dicionário com dados específicos da mensagem
            msg_id: ID opcional da mensagem (gerado automaticamente se não fornecido)
        """
        self.id = msg_id if msg_id else str(uuid.uuid4())
        self.type = msg_type
        self.srcip = srcip
        self.destip = destip
        self.timestamp = int(time.time())
        self.payload = payload if payload else {}
    
    def to_dict(self):
        """Converte a mensagem para dicionário."""
        return {
            "id": self.id,
            "type": self.type,
            "srcip": self.srcip,
            "destip": self.destip,
            "timestamp": self.timestamp,
            "payload": self.payload
        }
    
    def to_json(self):
        """Converte a mensagem para string JSON."""
        return json.dumps(self.to_dict())
    
    def to_bytes(self):
        """Converte a mensagem para bytes para transmissão na rede."""
        return self.to_json().encode('utf-8')
    
    @classmethod
    def from_dict(cls, data):
        """
        Cria uma mensagem a partir de um dicionário.
        
        Args:
            data: Dicionário com os campos da mensagem
        
        Returns:
            Instância de Message ou None se inválido
        """
        try:
            return cls(
                msg_type=data.get("type"),
                srcip=data.get("srcip"),
                destip=data.get("destip", "broadcast"),
                payload=data.get("payload", {}),
                msg_id=data.get("id")
            )
        except Exception:
            return None
    
    @classmethod
    def from_json(cls, json_str):
        """
        Cria uma mensagem a partir de uma string JSON.
        
        Args:
            json_str: String JSON
        
        Returns:
            Instância de Message ou None se a análise falhar
        """
        try:
            if isinstance(json_str, bytes):
                json_str = json_str.decode('utf-8')
            data = json.loads(json_str)
            return cls.from_dict(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
    
    @classmethod
    def from_bytes(cls, raw_bytes):
        """
        Cria uma mensagem a partir de bytes brutos.
        
        Args:
            raw_bytes: Bytes recebidos da rede
        
        Returns:
            Instância de Message ou None se a análise falhar
        """
        return cls.from_json(raw_bytes)
    
    def get_type(self):
        """Obtém o tipo da mensagem."""
        return self.type
    
    def get_payload(self):
        """Obtém o payload da mensagem."""
        return self.payload
    
    def get_src(self):
        """Obtém o IP de origem."""
        return self.srcip
    
    def get_dest(self):
        """Obtém o IP de destino."""
        return self.destip
    
    def __str__(self):
        """Representação em string da mensagem."""
        return f"Message(type={self.type}, src={self.srcip}, dest={self.destip}, id={self.id[:8]}...)"
    
    def __repr__(self):
        """Representação detalhada."""
        return f"Message({self.to_dict()})"


# Factory methods for creating specific message types

# TODO: add the other metrics to the flood message
    @classmethod
    def create_flood_message(cls, srcip, origin_flood ,flood_id=None, hop_count=0, video=None,start_timestamp=None):
        """Create a FLOOD message."""
        if start_timestamp is None:
            start_timestamp = time.time()

        payload = {
            "hop_count": hop_count,
            "video": video,
            "origin_ip":origin_flood,
            "start_timestamp": start_timestamp
        }
        return cls(
            msg_type=MsgType.FLOOD,
            srcip=srcip,
            destip="broadcast",
            payload=payload,
            msg_id=flood_id
        )


    @classmethod
    def create_alive_message(cls, srcip, destip):
        """Create an ALIVE heartbeat message."""
        return cls(
            msg_type=MsgType.ALIVE,
            srcip=srcip,
            destip=destip,
            payload={}
        )


    @classmethod
    def create_join_message(cls, srcip, node_id):
        """Create a JOIN message."""
        return cls(
            msg_type=MsgType.JOIN,
            srcip=srcip,
            destip="broadcast",
            payload={"node_id": node_id}
        )


    @classmethod
    def create_leave_message(cls, srcip, node_id):
        """Create a LEAVE message."""
        return cls(
            msg_type=MsgType.LEAVE,
            srcip=srcip,
            destip= node_id,
            
        )


    @classmethod
    def create_stream_start_message(cls, srcip, destip, video):
        """Create a STREAM_START message."""
        return cls(
            msg_type=MsgType.STREAM_START,
            srcip=srcip,
            destip=destip,
            payload={"video": video}
        )


    @classmethod
    def create_stream_end_message(cls, srcip, destip, video):
        """Create a STREAM_END message."""
        return cls(
            msg_type=MsgType.STREAM_END,
            srcip=srcip,
            destip=destip,
            payload={"video": video}
        )


    @classmethod
    def create_stream_data_message(cls, srcip, destip, video, sequence, data):
        """Create a STREAM_DATA message (UDP)."""
        return cls(
            msg_type=MsgType.STREAM_DATA,
            srcip=srcip,
            destip=destip,
            payload={
                "video": video,
                "sequence": sequence,
                "data": data
            }
        )
    
    
    @classmethod
    def create_register_message(cls, node_id, bootstrapper_ip):
        """Create a REGISTER message."""
        return cls(
            msg_type=MsgType.REGISTER,
            srcip=node_id,
            destip=bootstrapper_ip,  #
            payload={
                "node_id": node_id
            }
        )
    
    # neigh vão ser o resultado de uma lista de vizinhos fornecida pelo bootstrapper
    @classmethod
    def create_neighbour_message(cls, srcip, destip, neighbours_ip):
        """Create a NEIGHBOUR message."""
        return cls(
            msg_type=MsgType.NEIGHBOUR,
            srcip=srcip,
            destip=destip,
            payload={
                "neighbours": neighbours_ip
            }
        )


# Backward compatibility functions

def parse_message(raw_data):
    """
    Parse raw data into a Message object.
    
    Args:
        raw_data: Bytes or string containing JSON message
    
    Returns:
        Message instance or None if parsing fails
    """
    return Message.from_bytes(raw_data) if isinstance(raw_data, bytes) else Message.from_json(raw_data)


def get_message_type(msg):
    """
    Extract message type.
    
    Args:
        msg: Message instance or dictionary
    
    Returns:
        String message type or None
    """
    if isinstance(msg, Message):
        return msg.get_type()
    elif isinstance(msg, dict):
        return msg.get("type")
    return None