from tkinter import *
import tkinter.messagebox as tkMessageBox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os

from aux_files.RtpPacket import RtpPacket
import threading, os
from aux_files.aux_message import Message

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class ClienteGUI:
    
    # Initiation..
    def __init__(self, master, client):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.handler)
        self.client = client
        self.addr = client.node_ip
        self.port = client.RTPport
        self.rtspSeq = 0
        self.sessionId = 0
        self.requestSent = -1
        self.teardownAcked = 0
        self.frameNbr = 0
        self.createWidgets()
        #self.openRtpPort()
        # Don't call playMovie here - let user click Play button
        # self.playMovie()
  
  
        
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
        self.state = 1

        video_name = self.client.videos

        
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
            threading.Thread(target=self.client.send_tcp_message, args=(gateway_ip, start_msg)).start()
        
        else:
            tkMessageBox.showerror("Erro de Conexão", "Nenhum vizinho ativo encontrado.")

    
    def exitClient(self):
        """Teardown button handler."""
        self.client.stop_stream()
        self.master.destroy()
        # Remove cache file
        file_path = CACHE_FILE_NAME + "0" + CACHE_FILE_EXT # 0 is session ID
        if os.path.exists(file_path):
            os.remove(file_path) 

    def pauseMovie(self):
        """Pause button handler."""
        print("Not implemented...")
    
    def playMovie(self):
        """Play button handler."""
        # Create a new thread to listen for RTP packets
        threading.Thread(target=self.listenRtp).start()
        self.playEvent = threading.Event()
        self.playEvent.clear()

    
    def listenRtp(self):		
        """Listen for RTP packets."""
        while True:
            try:
                data = self.rtpSocket.recv(20480)
                if data:
                    rtpPacket = RtpPacket()
                    rtpPacket.decode(data)
                    
                    currFrameNbr = rtpPacket.seqNum()
                    print("Current Seq Num: " + str(currFrameNbr))
                                        
                    if currFrameNbr > self.frameNbr: # Discard the late packet
                        self.frameNbr = currFrameNbr
                        self.updateMovie(self.writeFrame(rtpPacket.getPayload()))
            except:
                # Stop listening upon requesting PAUSE or TEARDOWN
                if self.playEvent.isSet(): 
                    break
                
                self.rtpSocket.shutdown(socket.SHUT_RDWR)
                self.rtpSocket.close()
                break
                
    
    def writeFrame(self, data):
        """Write the received frame to a temp image file. Return the image file."""
        cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        file = open(cachename, "wb")
        file.write(data)
        file.close()
        
        return cachename
    
    def updateMovie(self, imageFile):
        """Update the image file as video frame in the GUI."""
        photo = ImageTk.PhotoImage(Image.open(imageFile))
        self.label.configure(image = photo, height=288) 
        self.label.image = photo
        
    
    def openRtpPort(self):
        """Open RTP socket binded to a specified port."""
        # Create a new datagram socket to receive RTP packets from the server
        self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Set the timeout value of the socket to 0.5sec
        self.rtpSocket.settimeout(0.5)
        
        try:
            # Bind the socket to the address using the RTP port
            self.rtpSocket.bind((self.addr, self.port))
            print('\nBind \n')
        except Exception as e:
            # Garante que a mensagem de erro usa self.rtpPort
            tkMessageBox.showwarning('Unable to Bind', f'Unable to bind PORT={self.rtpPort}. Error: {e}')

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
        
    def handler(self):
        """Handler on explicitly closing the GUI window."""
        self.pauseMovie()
        if tkMessageBox.askokcancel("Quit?", "Are you sure you want to quit?"):
            self.exitClient()
        else: # When the user presses cancel, resume playing.
            self.playMovie()

    def sendPing(self):
        neighbors = self.client.neighbors

        gateway = None
        for ip, active in neighbors.items():
            if active:
                gateway = ip
                break

        if not gateway:
            print("Nenhum vizinho ativo!")
            return

        print(f"[CLIENT] A enviar PING para {gateway}")

        msg = Message.create_ping_message(
            srcip=self.client.node_ip,
            destip=gateway
        )

        self.client.send_tcp_message(gateway, msg)
        self.client.stop_stream()
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