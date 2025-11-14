node_overlay = {
    # STREAMER conhece apenas C2
    "10.0.3.20": ["10.0.0.21"],

    # C2 conhece STREAMER e C1
    "10.0.0.21": ["10.0.3.20", "10.0.0.20"],

    # C1 conhece C2 e C5
    "10.0.0.20": ["10.0.0.21", "10.0.2.20"],

    # C5 conhece apenas C1
    "10.0.2.20": ["10.0.0.20"],
}




HOST = "10.0.4.20"
PORT = 5000
N_vizinho = 3
