# Message Class - Quick Reference Guide

## Overview

The `Message` class provides a **unified interface** for all overlay network messages, ensuring consistency across your server and node implementations.

## Message Structure

All messages follow this standard format:

```python
{
    "id": "unique-uuid",           # Auto-generated
    "type": "FLOOD",               # Message type
    "srcip": "192.168.1.100",      # Source IP
    "destip": "broadcast",         # Destination IP  
    "timestamp": 1234567890,       # Unix timestamp (auto-generated)
    "payload": {...}               # Message-specific data
}
```

## Creating Messages

### Method 1: Direct Creation

```python
from aux_files.aux_message import Message, MsgType

msg = Message(
    msg_type=MsgType.FLOOD,
    srcip="192.168.1.100",
    destip="broadcast",
    payload={"hop_count": 0}
)
```

### Method 2: Factory Functions (Recommended)

```python
from aux_files.aux_message import create_flood_message

msg = create_flood_message(
    srcip="192.168.1.100",
    hop_count=0
)
```

## Available Factory Functions

```python
create_flood_message(srcip, flood_id=None, hop_count=0, **kwargs)
create_alive_message(srcip, destip)
create_join_message(srcip, node_id)
create_leave_message(srcip, node_id, reason="")
create_stream_start_message(srcip, destip, stream_id)
create_stream_end_message(srcip, destip, stream_id)
create_stream_data_message(srcip, destip, stream_id, sequence, data)
```

## Sending Messages

### TCP

```python
import socket

# Create message
msg = create_flood_message(srcip="192.168.1.100", hop_count=1)

# Send
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(("192.168.1.101", 6000))
sock.send(msg.to_bytes())  # ← Converts to bytes automatically
sock.close()
```

### UDP

```python
# Create message
msg = create_stream_data_message(
    srcip="192.168.1.100",
    destip="192.168.1.101",
    stream_id="video1",
    sequence=42,
    data="base64_encoded_data"
)

# Send
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.sendto(msg.to_bytes(), ("192.168.1.101", 7000))
sock.close()
```

## Receiving Messages

```python
# In your server/listener
raw_data = conn.recv(65535)

# Parse into Message object
msg = Message.from_bytes(raw_data)

if msg:
    # Access message fields
    msg_type = msg.get_type()
    payload = msg.get_payload()
    src = msg.get_src()
    
    # Process message...
```

## Message Methods

### Serialization

```python
msg.to_dict()    # → Dictionary
msg.to_json()    # → JSON string
msg.to_bytes()   # → Bytes (ready for network)
```

### Deserialization

```python
Message.from_dict(dict_data)    # From dictionary
Message.from_json(json_string)  # From JSON string
Message.from_bytes(raw_bytes)   # From network bytes
```

### Access Methods

```python
msg.get_type()     # → Message type string
msg.get_payload()  # → Payload dictionary
msg.get_src()      # → Source IP
msg.get_dest()     # → Destination IP
```

## Usage in Control Server

```python
from aux_files.aux_message import Message, MsgType

class ControlServer:
    
    def _handle_connection(self, conn, addr):
        sender_ip = addr[0]
        
        # Receive
        raw_data = conn.recv(65535)
        
        # Parse
        msg = Message.from_bytes(raw_data)
        if not msg:
            print("Invalid message")
            return
        
        # Process
        self.handler_callback(msg, sender_ip)
```

## Usage in Node

```python
from aux_files.aux_message import Message, MsgType, create_flood_message

class Node:
    
    def handle_message(self, msg, sender_ip):
        """Called by server when message arrives."""
        
        msg_type = msg.get_type()
        payload = msg.get_payload()
        
        if msg_type == MsgType.FLOOD:
            self.handle_flood(msg, sender_ip)
        elif msg_type == MsgType.ALIVE:
            self.handle_alive(msg, sender_ip)
        # ... etc
    
    def send_flood_to_neighbors(self):
        """Send flood to all neighbors."""
        
        msg = create_flood_message(
            srcip=self.node_ip,
            hop_count=0
        )
        
        for neighbor_ip in self.neighbors:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((neighbor_ip, 6000))
            sock.send(msg.to_bytes())
            sock.close()
```

## Message Types

Use `MsgType` constants to avoid typos:

```python
from aux_files.aux_message import MsgType

MsgType.FLOOD          # "FLOOD"
MsgType.ALIVE          # "ALIVE"
MsgType.JOIN           # "JOIN"
MsgType.LEAVE          # "LEAVE"
MsgType.STREAM_START   # "STREAM_START"
MsgType.STREAM_END     # "STREAM_END"
MsgType.STREAM_DATA    # "STREAM_DATA"
MsgType.ALIVE_ACK      # "ALIVE_ACK"
```

## Benefits

✅ **Consistency** - All messages have the same structure  
✅ **Type Safety** - Use constants instead of strings  
✅ **Auto Fields** - ID and timestamp generated automatically  
✅ **Easy Serialization** - One method to convert to bytes  
✅ **Easy Parsing** - One method to parse from bytes  
✅ **Clean API** - Clear, intuitive methods  
✅ **IDE Support** - Autocomplete and type hints  

## Migration from Old Code

### Before (Dictionary):
```python
msg = {
    "id": str(uuid.uuid4()),
    "type": "FLOOD",
    "srcip": "192.168.1.100",
    "payload": {"hop_count": 0}
}
sock.send(json.dumps(msg).encode())
```

### After (Message Class):
```python
msg = create_flood_message(srcip="192.168.1.100", hop_count=0)
sock.send(msg.to_bytes())
```

Much cleaner! 🎓
