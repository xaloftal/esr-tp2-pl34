# overlay_nodes.py
node_overlay = {

    "10.0.1.2": ["10.0.2.2", "10.0.3.2", "10.0.4.2"],   # SERVIDOR
    "10.0.2.2": ["10.0.1.2", "10.0.3.2"],
    "10.0.3.2": ["10.0.1.2", "10.0.2.2", "10.0.4.2"],
    "10.0.4.2": ["10.0.1.2", "10.0.3.2", "10.0.5.2", "10.0.6.2"],
    "10.0.5.2": ["10.0.4.2", "10.0.6.2"],
    "10.0.6.2": ["10.0.4.2", "10.0.5.2"],
}

# Endereço do bootstrapper (nó separado, fora da overlay)
HOST = "10.0.18.21"
PORT = 5000

# Número de vizinhos pretendidos se futuramente quiseres gerar vizinhos dinâmicos
N_vizinho = 3
