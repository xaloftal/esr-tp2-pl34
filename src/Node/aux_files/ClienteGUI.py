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
        self.is_paused = False
        
        # Ligar o callback do cliente à GUI para receber mensagens PONG
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
        """Setup button handler."""
        # Acede ao vídeo guardado no ControlClient
        video_name = self.client.video 
        
        if not video_name:
            tkMessageBox.showerror("Erro", "Nenhum vídeo definido no arranque do cliente.")
            return

        my_neighbors = self.client.neighbors 
        
        gateway_ip = None

        # Procura o primeiro vizinho ativo 
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
            # Envia pedido numa thread para não bloquear GUI
            threading.Thread(target=self.client.send_tcp_message, args=(gateway_ip, start_msg)).start()
        
        else:
            tkMessageBox.showerror("Erro de Conexão", "Nenhum vizinho ativo encontrado.")

    def exitClient(self):
        """Teardown button handler."""
        self.client.stop_stream()
        self.master.destroy()
        
        # --- CORREÇÃO: REMOVIDA A LÓGICA DE APAGAR O FICHEIRO CACHE-0.JPG ---
        # Não é mais necessário, pois o ficheiro não é criado.
        file_path = CACHE_FILE_NAME + "0" + CACHE_FILE_EXT
        if os.path.exists(file_path):
             pass 

    def playMovie(self):
        """Play button handler."""
        # Inicia a thread de escuta RTP no ControlClient, passando o callback de update
        # NOTA: O ControlClient é que gere o socket!
        self.is_paused = False
        threading.Thread(target=self.client.listen_rtp, args=(self.updateMovie,), daemon=True).start()
        
    def pauseMovie(self):
        """Pause button handler."""
        self.is_paused = True

    def updateMovie(self, image_obj): # <<--- AGORA ESPERA OBJETO Image, NÃO NOME DE FICHEIRO
        """Update the image file as video frame in the GUI."""
        if not self.is_paused:
            try:
                # O image_obj JÁ É a imagem carregada na memória (PIL Image)
                photo = ImageTk.PhotoImage(image_obj)
                
                self.label.configure(image = photo, height=288) 
                self.label.image = photo
            except Exception as e:
                pass

    def sendPing(self):
        self.pongLabel.config(text="") # limpar resposta anterior
        
        neighbors = self.client.neighbors
        
        gateway = None
        for ip, active in neighbors.items():
            if active:
                gateway = ip
                break
        
        if not gateway:
            print("Nenhum vizinho ativo!")
            self.pongLabel.config(text="Sem vizinhos", fg="red")
            return
        
        print(f"[CLIENT] A enviar PING para {gateway}")
        
        msg = Message.create_ping_message(
            srcip=self.client.node_ip,
            destip=gateway
        )
        self.client.send_tcp_message(gateway, msg)

    def gui_msg_handler(self, msg_text):
        """Callback para receber mensagens do cliente (ex: PONG)"""
        if "PONG" in msg_text:
             self.pongLabel.config(text="PONG RECEBIDO!", fg="blue")

    def handler(self):
        """Handler on explicitly closing the GUI window."""
        if tkMessageBox.askokcancel("Quit?", "Are you sure you want to quit?"):
            self.exitClient()