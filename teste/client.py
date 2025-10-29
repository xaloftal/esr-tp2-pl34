import socket

HOST = '127.0.0.1'   # IP do servidor de bootstrap
PORT = 8000          # Porta do servidor de bootstrap

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, PORT))

    # Enviar JOIN automaticamente
    local_ip = '127.0.0.1'
    local_port = s.getsockname()[1]  # Porta usada pelo cliente
    join_msg = f"JOIN {local_ip} {local_port}"
    s.sendall(join_msg.encode())

    print(f"[CLIENTE] JOIN enviado: {join_msg}")

    # Receber ID e lista de nós
    nodes = []
    node_id = None

    buffer = ""  # para guardar mensagens incompletas

    while True:
        data = s.recv(1024).decode()

        if not data:
            break  # ligação fechada

        buffer += data  # acumula texto

        # processa cada linha recebida
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()

            if line.startswith("OK"):
                node_id = line.split()[1]
                print(f"[CLIENTE] Recebi Node ID: {node_id}")

            elif line == "END":
                print("[CLIENTE] Lista de nós na rede:")
                for node in nodes:
                    print(" ", node)
                print("[CLIENTE] Fim da lista. Encerrado.")
                s.close()
                exit()

            else:
                nodes.append(line)
