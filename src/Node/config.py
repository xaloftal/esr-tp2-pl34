# Ficheiro: src/Node/config.py
import sys

# --- Configs do Bootstrapper ---
# Lê o IP do bootstrapper da linha de comando
# (o 4º argumento, ex: python3 node.py n1 10.0.0.20 10.0.20.20)
try:
    BOOTSTRAPPER_IP = sys.argv[3]
except IndexError:
    print("Erro: IP do Bootstrapper não fornecido.")
    print("Uso: python3 node.py NODE_ID NODE_IP BOOTSTRAPPER_IP [--server]")
    sys.exit(1)

BOOTSTRAPPER_PORT = 5000 # Porta do bootstrapper

# --- Configs dos Nós da Overlay ---
# Porta TCP onde CADA nó vai escutar por msgs de controlo (FLOOD, etc.)
NODE_TCP_PORT = 6000