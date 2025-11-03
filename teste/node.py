import socket
import threading

BOOTSTRAPPER_IP = "10.0.0.20"  # muda para o IP do bootstrapper no CORE
BOOTSTRAPPER_PORT = 5000
UDP_PORT = 6000

neighbors = []

def join_overlay():
    global neighbors
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((BOOTSTRAPPER_IP, BOOTSTRAPPER_PORT))
    print("[NODE] Connected to Bootstrapper")

    data = s.recv(1024).decode()
    print("[NODE] Neighbors received:", data)
    neighbors = eval(data)
    s.close()

def listen_udp():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", UDP_PORT))
    print(f"[NODE] Listening for video on UDP {UDP_PORT}...")

    frame_count = 0
    with open("received_video.mjpeg", "ab") as f:
        while True:
            data, _ = sock.recvfrom(65536)
            if not data:
                break
            f.write(data)
            frame_count += 1
            if frame_count % 100 == 0:
                print(f"[NODE] Recebidas {frame_count} frames...")

if __name__ == "__main__":
    join_overlay()
    listen_thread = threading.Thread(target=listen_udp, daemon=True)
    listen_thread.start()
    listen_thread.join()
