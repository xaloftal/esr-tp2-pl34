from tkinter import *
import tkinter.messagebox as tkMessageBox
from PIL import Image, ImageTk
import threading, os
from aux_files.aux_message import Message
import io

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class ClienteGUI:
    
    def __init__(self, master, client):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.handler)
        self.client = client
        self.is_paused = False
        
        # Bind client callback to GUI to receive PONG signals
        self.client.gui_callback = self.gui_msg_handler
        
        self.createWidgets()
  
    def createWidgets(self):
        """Build GUI."""
        # Create Setup button
        self.setup = Button(self.master, width=20, padx=3, pady=3)
        self.setup["text"] = "Setup"
        self.setup["command"] = self.setupMovie
        self.setup.grid(row=1, column=0, padx=2, pady=2)        

        # Create Play button        
        self.start = Button(self.master, width=20, padx=3, pady=3)
        self.start["text"] = "Play"
        self.start["command"] = self.playMovie
        self.start.grid(row=1, column=1, padx=2, pady=2)
        
        # create Pause button
        self.pause = Button(self.master, width=20, padx=3, pady=3)
        self.pause["text"] = "Pause"
        self.pause["command"] = self.pauseMovie
        self.pause.grid(row=1, column=2, padx=2, pady=2)
        
        # Create Teardown button
        self.teardown = Button(self.master, width=20, padx=3, pady=3)
        self.teardown["text"] = "Teardown"
        self.teardown["command"] =  self.exitClient
        self.teardown.grid(row=1, column=3, padx=2, pady=2)
        
        # Create Ping button
        self.ping = Button(self.master, width=20, padx=3, pady=3)
        self.ping["text"] = "PING"
        self.ping["command"] = self.sendPing
        self.ping.grid(row=2, column=0, padx=2, pady=2)

        # Label para mostrar resposta PONG
        self.pongLabel = Label(self.master, text="", fg="green")
        self.pongLabel.grid(row=2, column=1, padx=2, pady=2)

        # Create a label to display the movie
        self.label = Label(self.master, height=19)
        self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 
    
    def setupMovie(self):
        """
        Handler for the SETUP button.
        Selects a neighbor and sends the SETUP request.
        """
        # Access video name defined in ControlClient
        video_name = self.client.video 
        
        if not video_name:
            tkMessageBox.showerror("Erro", "Nenhum vídeo definido no arranque do cliente.")
            return

        my_neighbors = self.client.neighbors 
        gateway_ip = None

        # Find the first active neighbor to act as gateway
        for ip, is_active in my_neighbors.items():
            if is_active:
                gateway_ip = ip
                break
        
        if gateway_ip:
            print(f"[ClientGUI] A pedir '{video_name}' ao vizinho: {gateway_ip}")
            
            start_msg = Message.create_stream_start_message(
                srcip=self.client.node_ip, 
                destip=gateway_ip, 
                video=video_name
            )
            
            # Send request in a separate thread to avoid blocking the GUI
            threading.Thread(target=self.client.send_tcp_message, args=(gateway_ip, start_msg)).start()
        
        else:
            tkMessageBox.showerror("Erro de Conexão", "Nenhum vizinho ativo encontrado.")

    def exitClient(self):
        """
        Handler for the TEARDOWN button.
        Stops the stream and closes the window.
        """
        self.client.stop_stream()
        
        # Allow time for the TEARDOWN message to be sent before killing the process
        self.master.after(200, self.master.destroy)

    def playMovie(self):
        """
        Handler for the PLAY button.
        """
        # If just paused, resume
        self.is_paused = False

        # Start the ControlClient RTP listener thread with the update callback
        threading.Thread(target=self.client.listen_rtp, args=(self.updateMovie,), daemon=True).start()
        
    def pauseMovie(self):
        """Pause button handler."""
        self.is_paused = True

    def updateMovie(self, image_data):
        """
        Callback triggered by ControlClient when a frame arrives.
        Receives BYTES (image_data) instead of a filename.
        Schedules the UI update on the Main Thread to be Thread-Safe.
        """
        if not self.is_paused:
            # Schedule execution on the main thread
            self.master.after(0, self._update_image_internal, image_data)
            
    def _update_image_internal(self, image_data):
        """
        Internal method running on Main Thread.
        Converts bytes to Image and updates the Tkinter Label.
        """
        try:
            # Convert bytes to an in-memory stream
            image_stream = io.BytesIO(image_data)
            
            # Open image from RAM
            im = Image.open(image_stream)
            photo = ImageTk.PhotoImage(im)
            
            self.label.configure(image=photo, height=288) 
            self.label.image = photo
        except Exception as e:
            # Ignore corrupted frames to prevent crashes
            pass

    def sendPing(self):
        """
        Sends a PING message to the connected gateway to test latency/path.
        """
        self.pongLabel.config(text="") # Clear previous status
        
        neighbors = self.client.neighbors
        gateway = None
        
        # Find active gateway
        for ip, active in neighbors.items():
            if active:
                gateway = ip
                break
        
        if not gateway:
            print("[ClientGUI] Nenhum vizinho ativo!")
            self.pongLabel.config(text="Sem vizinhos", fg="red")
            return
        
        print(f"[ClientGUI] A enviar PING para {gateway}")
        
        msg = Message.create_ping_message(
            srcip=self.client.node_ip,
            destip=gateway
        )
        self.client.send_tcp_message(gateway, msg)

    def gui_msg_handler(self, msg_text):
        """Callback to handle messages coming from ControlClient (e.g., PONG)."""
        if "PONG" in msg_text:
             self.pongLabel.config(text="PONG RECEBIDO!", fg="blue")

    def handler(self):
        """Handler for explicitly closing the GUI window (X button)."""
        if tkMessageBox.askokcancel("Sair?", "Tem a certeza que quer sair?"):
            self.exitClient()