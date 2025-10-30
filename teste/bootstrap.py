import socket
import json
import os

NODES_FILE = "nodes.json"
HOST = "0.0.0.0"
PORT = 7000


def load_nodes():
    if not os.path.exists(NODES_FILE):
        return []
    with open(NODES_FILE, "r") as f:
        return json.load(f)


def save_nodes(nodes):
    with open(NODES_FILE, "w") as f:
        json.dump(nodes, f, indent=4)


def update_neighbors(nodes):
    """Atualiza pred e succ para todos os nós conforme o anel."""
    if len(nodes) == 1:
        nodes[0]["pred"] = None
        nodes[0]["succ"] = None
        return nodes

    ids_sorted = sorted(nodes, key=lambda x: x["id"])
    total = len(ids_sorted)

    for i, node in enumerate(ids_sorted):
        pred_node = ids_sorted[i - 1] if total > 1 else None
        succ_node = ids_sorted[(i + 1) % total] if total > 1 else None

        node["pred"] = pred_node["id"] if pred_node else None
        node["succ"] = succ_node["id"] if succ_node else None

    return ids_sorted


def get_node_info(nodes, node_id):
    for n in nodes:
        if n["id"] == node_id:
            return n
    return None


def main():
    print(f"[BOOTSTRAP] A iniciar em {HOST}:{PORT} ...")

    nodes = load_nodes()
    print(f"[BOOTSTRAP] {len(nodes)} nó(s) carregados do ficheiro.")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()

    print("[BOOTSTRAP] A aguardar ligações...\n")

    while True:
        conn, addr = server.accept()
        data = conn.recv(1024).decode().strip()

        if not data:
            conn.close()
            continue

        parts = data.split()
        if parts[0] != "JOIN":
            conn.close()
            continue

        ip = parts[1]
        port = int(parts[2])

        new_id = 1 if not nodes else nodes[-1]["id"] + 1
        new_node = {"id": new_id, "ip": ip, "port": port}

        nodes.append(new_node)
        nodes = update_neighbors(nodes)
        save_nodes(nodes)

        # Preparar resposta para o nó que entrou
        info = get_node_info(nodes, new_id)

        # Obter info completa dos vizinhos
        pred_node = get_node_info(nodes, info["pred"]) if info["pred"] else None
        succ_node = get_node_info(nodes, info["succ"]) if info["succ"] else None

        response = {
            "node": new_id,
            "predecessor": pred_node,
            "successor": succ_node
        }

        conn.sendall(json.dumps(response).encode())
        conn.close()

        # LOGS
        print(f"[JOIN] Novo nó entrou: ID={new_id}, IP={ip}, PORT={port}")
        print("[NODES] Topologia atual do anel:")
        for n in nodes:
            print(f"  {n['id']} → pred={n['pred']} | succ={n['succ']}  ({n['ip']}:{n['port']})")
        print("-" * 45)


if __name__ == "__main__":
    main()
