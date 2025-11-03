import socket
import threading
import cv2
import numpy as np

BOOTSTRAPPER_IP = "10.0.0.20"  # muda para o IP do bootstrapper
BOOTSTRAPPER_PORT = 5000
UDP_PORT = 6000  # porta onde este node vai receber frames

neighbors = []

def join_overlay():
    global neighbors
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((BOOTSTRAPPER_IP, BOOTSTRAPPER_PORT))
    print("[NODE] Connected to Bootstrapper")

    data = s.recv(1024).decode()
    print("[NODE] Neighbors received:", data)
    neighbors = eval(data)  # converte a string enviada para tuplo/lista
    s.close()

def listen_udp():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", UDP_PORT))
    print(f"[NODE] Listening for video on UDP {UDP_PORT}...")
    while True:
        data, _ = sock.recvfrom(65536)
        npdata = np.frombuffer(data, dtype=np.uint8)
        frame = cv2.imdecode(npdata, cv2.IMREAD_COLOR)
        if frame is not None:
            cv2.imshow("Video Ronaldo", frame)
            if cv2.waitKey(1) == ord('q'):
                break
    sock.close()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    join_overlay()
    listen_thread = threading.Thread(target=listen_udp, daemon=True)
    listen_thread.start()
    listen_thread.join()
