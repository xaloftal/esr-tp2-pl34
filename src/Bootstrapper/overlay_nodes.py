# Ficheiro: src/Bootstrapper/overlay_nodes.py

# Dicionário que mapeia o IP de um nó à lista de IPs dos seus vizinhos
# Esta é a topologia "manual" lida pelo bootstrapper.

node_overlay = {
    # STREAMER (10.0.0.20) conhece apenas C2
    "10.0.0.20": ["10.0.0.21"],

    # C2 (10.0.0.21) conhece STREAMER (20) e C1 (1.2)
    "10.0.0.21": ["10.0.0.20", "10.0.1.2"],

    # C1 (10.0.1.2) conhece C2 (21) e C5 (2.20)
    "10.0.1.2": ["10.0.0.21", "10.0.2.20"],

    # C5 (10.0.2.20) conhece apenas C1 (1.2)
    "10.0.2.20": ["10.0.1.2"],
}