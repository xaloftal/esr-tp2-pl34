# File: src/Node/config.py
import sys

# --- BOOTSTRAPPER CONFIGURATION ---
# Reads the bootstrapper IP from the command line (4th argument).
# Usage: python3 node.py NODE_ID NODE_IP BOOTSTRAPPER_IP [--server]
try:
    BOOTSTRAPPER_IP = sys.argv[3]
except IndexError:
    print("Error: Bootstrapper IP not provided.")
    print("Usage: python3 node.py NODE_ID NODE_IP BOOTSTRAPPER_IP [--server]")
    sys.exit(1)

BOOTSTRAPPER_PORT = 5000 # Bootstrapper listening port

# --- OVERLAY NODE CONFIGURATION ---
# TCP port where EACH node listens for control messages (FLOOD, TEARDOWN, etc.)
NODE_TCP_PORT = 6000

# UDP port used for receiving RTP video streams
NODE_RTP_PORT = 7000 


# --- HEARTBEAT / FAILURE DETECTION CONFIGURATION ---
HEARTBEAT_INTERVAL = 2      # Frequency (in seconds) for sending ALIVE messages
FAIL_TIMEOUT = 25           # Time (in seconds) to wait before considering a node suspect (Silence RTP/ALIVE)
MAX_FAILS = 3               # Maximum number of consecutive timeouts before marking a neighbor/route as inactive (Failure Count)