from tkinter import *
import tkinter.messagebox as tkMessageBox
from PIL import Image, ImageTk
import threading, os
from aux_files.aux_message import Message

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class ClienteGUI:
    
    def __init__(self, master, client):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.handler)
        self.client = client
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
        
        # Create Pause button            
        self.pause = Button(self.master, width=20, padx=3, pady=3)
        self.pause["text"] = "Pause"
        self.pause["command"] = self.pauseMovie
        self.pause.grid(row=1, column=2, padx=2, pady=2)
        
        # Create Teardown button
        self.teardown = Button(self.master, width=20, padx=3, pady=3)
        self.teardown["text"] = "Teardown"
        self.teardown["command"] =  self.exitClient
        self.teardown.grid(row=1, column=3, padx=2, pady=2)
        
        # Create a label to display the movie
        self.label = Label(self.master, height=19)
        self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 
    
    def setupMovie(self):
        """Setup button handler."""
        # Acede ao vídeo guardado no ControlClient
        video_name = self.client.video 
        
        if not video_name:
            tkMessageBox.showerror("Erro", "Nenhum vídeo definido no arranque do cliente.")
            return

        my_neighbors = self.client.neighbors 
        
        gateway_ip = None
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
            threading.Thread(target=self.client.send_tcp_message, args=(gateway_ip, start_msg)).start()
        else:
            tkMessageBox.showerror("Erro de Conexão", "Nenhum vizinho ativo encontrado.")

    
    def exitClient(self):
        """Teardown button handler."""
        self.master.destroy()
        # Remove cache file
        file_path = CACHE_FILE_NAME + "0" + CACHE_FILE_EXT # 0 is session ID
        if os.path.exists(file_path):
            os.remove(file_path) 

    def pauseMovie(self):
        print("Pause não implementado...")
    
    def playMovie(self):
        """Play button handler."""
        threading.Thread(target=self.client.listen_rtp, args=(self.updateMovie,), daemon=True).start()
    
    def updateMovie(self, imageFile):
        """Update the image file as video frame in the GUI."""
        try:
            # Tenta abrir a imagem
            im = Image.open(imageFile)
            photo = ImageTk.PhotoImage(im)
            
            self.label.configure(image = photo, height=288) 
            self.label.image = photo
        except Exception as e:
            pass

    def handler(self):
        """Handler on explicitly closing the GUI window."""
        if tkMessageBox.askokcancel("Quit?", "Are you sure you want to quit?"):
            self.exitClient()