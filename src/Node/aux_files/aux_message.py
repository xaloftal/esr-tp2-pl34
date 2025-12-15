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
    PING = "PING"
    PONG = "PONG"
    TEARDOWN = "TEARDOWN"
    PING_TEST = "PING_TEST"
    



class Message:
    """
    Message class for communication between nodes.
    
    Message structure:
    {
        "id": unique ID,
        "type": message type (from MsgType),
        "srcip": source IP address,
        "destip": destination IP address (or "broadcast"),
        "timestamp": when the message was created,
        "payload": message-specific data
    }
    """
    
    def __init__(self, msg_type, srcip, destip="broadcast", payload=None, msg_id=None):
        """
        Creates a new message.
        
        Args:
            msg_type: Message type (use MsgType constants)
            srcip: Source IP address
            destip: Destination IP address (default: "broadcast")
            payload: Dictionary with message-specific data
            msg_id: Optional message ID (automatically generated if None)
        """
        self.id = msg_id if msg_id else str(uuid.uuid4())
        self.type = msg_type
        self.srcip = srcip
        self.destip = destip
        self.timestamp = int(time.time())
        self.payload = payload if payload else {}
    
    def to_dict(self):
        """Converts the message to a dictionary."""
        return {
            "id": self.id,
            "type": self.type,
            "srcip": self.srcip,
            "destip": self.destip,
            "timestamp": self.timestamp,
            "payload": self.payload
    }
    
    def to_json(self):
        """Converts the message to a JSON string."""
        return json.dumps(self.to_dict())
    
    def to_bytes(self):
        """Converts the message to bytes for network transmission."""
        return self.to_json().encode('utf-8')
    
    @classmethod
    def from_dict(cls, data):
        """
        Creates a message from a dictionary.
        
        Args:
            data: Dictionary with message fields
        
        Returns:
            Message instance or None if invalid
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
        Creates a message from a JSON string.
        
        Args:
            json_str: JSON string
        
        Returns:
            Message instance or None if parsing fails
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
        Creates a message from raw bytes.
        
        Args:
            raw_bytes: Bytes received from the network
        
        Returns:
            Message instance or None if parsing fails
        """
        return cls.from_json(raw_bytes)
    
    def get_type(self):
        """Gets the message type."""
        return self.type
    
    def get_payload(self):
        """Gets the message payload."""
        return self.payload
    
    def get_src(self):
        """Gets the source IP."""
        return self.srcip
    
    def get_dest(self):
        """Gets the destination IP."""
        return self.destip
    
    def __str__(self):
        """String representation of the message."""
        return f"Message(type={self.type}, src={self.srcip}, dest={self.destip}, id={self.id[:8]}...)"
    
    def __repr__(self):
        """Detailed representation."""
        return f"Message({self.to_dict()})"



    @classmethod
    def create_flood_message(cls, srcip, origin_flood ,flood_id=None, hop_count=0, video=None, start_timestamp=None,
                             accumulated_latency=0, accumulated_jitter=0, accumulated_loss=0): 
        """Create a FLOOD message."""
        if start_timestamp is None:
            start_timestamp = time.time()

        payload = {
            "hop_count": hop_count,
            "video": video,
            "origin_ip":origin_flood,
            "start_timestamp": start_timestamp,
            "accumulated_latency": accumulated_latency,
            "accumulated_jitter": accumulated_jitter,
            "accumulated_loss": accumulated_loss
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
    def create_teardown_message(cls, srcip, destip, video):
        """Create a TEARDOWN message."""
        return cls(
            msg_type=MsgType.TEARDOWN,
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
            destip=bootstrapper_ip,
            payload={
                "node_id": node_id
            }
        )
    
    @classmethod
    def create_neighbour_message(cls, srcip, destip, neighbours_ip):
        """Create a NEIGHBOUR message. Neighbors list provided by bootstrapper."""
        return cls(
            msg_type=MsgType.NEIGHBOUR,
            srcip=srcip,
            destip=destip,
            payload={
                "neighbours": neighbours_ip
            }
        )

    # PING/PONG and PING_TEST methods (for path testing)
    
    @classmethod
    def create_ping_message(cls, srcip, destip):
        """Create a PING message."""
        return cls(
            msg_type=MsgType.PING,
            srcip=srcip,
            destip=destip
        )

    @classmethod
    def create_pong_message(cls, srcip, destip):
        """Create a PONG message."""
        return cls(
            msg_type=MsgType.PONG,
            srcip=srcip,
            destip=destip
        )
    @classmethod
    def create_pingtest_message(cls, srcip, destip, video_name, current_path=None):
        """
        Creates a PING_TEST message that accumulates the path traversed.
        """
        if current_path is None:
            current_path = []
            
        return cls(
            msg_type=MsgType.PING_TEST,
            srcip=srcip,
            destip=destip,
            payload={
                "video": video_name,
                "path": current_path # List that will grow: ['S1', 'N2', 'N5', ...]
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