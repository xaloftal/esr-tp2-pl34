from enum import Enum, auto
import uuid
import json

class MsgType:
    """Message type"""
    
    # Control messages (TCP)
    FLOOD = "FLOOD"
    ALIVE = "ALIVE"
    JOIN = "JOIN"
    LEAVE = "LEAVE"
    STREAM_START = "STREAM_START"
    STREAM_END = "STREAM_END"
    
    # Data messages (UDP)
    STREAM_DATA = "STREAM_DATA"
    
    # Acknowledgments
    ALIVE_ACK = "ALIVE_ACK"


# Helper functions for message creation
def create_message(msg_id = uuid.uuid4(), msg_type, srcip, destip, data=None):
    """
    Creates a standard message dictionary.
    """
    return {
        "id": msg_id,
        "type": msg_type,
        "srcip" : srcip,
        "destip": destip,
        "payload": data or {}
    }


def parse_message(raw_data):
    """
    Parses raw JSON string into a message dictionary
    """
    try:
        msg = json.loads(raw_data)
        return msg
    except json.JSONDecodeError:
        return None


def get_message_type(msg):
    """
    Extracts the message type from a parsed message.
    
    Args:
        msg: Dictionary with 'type' field
    
    Returns:
        Message type string or None
    """
    return msg.get("type") if msg else None