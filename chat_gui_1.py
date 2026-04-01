"""
ChatNet v5 - Full WhatsApp Structure
Left Panel: Chats list (rooms + DMs)
Right Panel: Active chat window
Top: Search, Profile, New Group, Status
"""
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import threading, os, json, socket, base64, struct, hashlib, datetime, time

# ══════════════════════════════════════════════════════════════════════════════
#  BACKEND
# ══════════════════════════════════════════════════════════════════════════════
class ChatClient:
    def __init__(self, host, port, cb):
        self.host=host; self.port=int(port); self.on_packet=cb
        self.sock=None; self.connected=False; self.username=None

    def connect(self):
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.sock.connect((self.host,self.port)); self.connected=True

    def send_packet(self,p):
        d=json.dumps(p).encode('utf-8')
        self.sock.sendall(struct.pack('>I',len(d))+d)

    def recv_packet(self):
        r=self._exact(4)
        if not r: return None
        (n,)=struct.unpack('>I',r); r=self._exact(n)
        return json.loads(r.decode('utf-8')) if r else None

    def _exact(self,n):
        buf=b''
        while len(buf)<n:
            c=self.sock.recv(n-len(buf))
            if not c: return None
            buf+=c
        return buf

    def authenticate(self,username,password,action='login',about=''):
        self.send_packet({"type":"auth","username":username,"password":password,
                          "action":action,"about":about})
        r=self.recv_packet()
        if r and r.get('type')=='auth_ok': self.username=username; return True,None
        return False,(r.get('reason','Unknown') if r else 'No response')

    def join_room(self,room):
        self.send_packet({"type":"join","room":room})
        r=self.recv_packet(); return r and r.get('type')=='join_ok'

    def start_listener(self):
        threading.Thread(target=self._loop,daemon=True).start()

    def _loop(self):
        while self.connected:
            try:
                pkt=self.recv_packet()
                if pkt is None: self.on_packet({"type":"disconnected"}); break
                self.on_packet(pkt)
            except Exception as e:
                self.on_packet({"type":"error","msg":str(e)}); break

    def send_message(self,text,to=None,reply_to=None):
        p={"type":"message","text":text}
        if to: p["to"]=to
        if reply_to: p["reply_to"]=reply_to
        self.send_packet(p)

    def send_file(self,filepath,to=None):
        fname=os.path.basename(filepath); size=os.path.getsize(filepath)
        ext=fname.split('.')[-1].lower()
        ftype='image' if ext in ['png','jpg','jpeg','gif','bmp','webp'] else \
              'video' if ext in ['mp4','avi','mov','mkv'] else \
              'audio' if ext in ['mp3','wav','ogg'] else 'other'
        with open(filepath,'rb') as f: data=base64.b64encode(f.read()).decode()
        p={"type":"file","filename":fname,"size":size,"data":data,"file_type":ftype}
        if to: p["to"]=to
        self.send_packet(p); return fname,size,ftype

    def save_file(self,pkt,save_dir="downloads"):
        os.makedirs(save_dir,exist_ok=True)
        fname=pkt.get('filename','file'); path=os.path.join(save_dir,fname)
        base,ext=os.path.splitext(path); i=1
        while os.path.exists(path): path=f"{base}_{i}{ext}"; i+=1
        with open(path,'wb') as f: f.write(base64.b64decode(pkt.get('data','')))
        return path

    def call_request(self,to,call_type='voice'): self.send_packet({"type":"call_request","to":to,"call_type":call_type})
    def call_accept(self,call_id): self.send_packet({"type":"call_accept","call_id":call_id})
    def call_reject(self,call_id): self.send_packet({"type":"call_reject","call_id":call_id})
    def call_end(self,call_id): self.send_packet({"type":"call_end","call_id":call_id})
    def send_audio(self,call_id,b64): self.send_packet({"type":"audio_chunk","call_id":call_id,"audio":b64})
    def send_video(self,call_id,b64): self.send_packet({"type":"video_chunk","call_id":call_id,"frame":b64})
    def send_reaction(self,emoji): self.send_packet({"type":"reaction","emoji":emoji})
    def set_status(self,s): self.send_packet({"type":"status_update","status":s})
    def send_typing(self):
        try: self.send_packet({"type":"typing"})
        except: pass
    def stop_typing(self):
        try: self.send_packet({"type":"stop_typing"})
        except: pass
    def get_users(self): self.send_packet({"type":"get_users"})
    def update_profile(self,about): self.send_packet({"type":"update_profile","about":about})
    def create_group(self,name,members): self.send_packet({"type":"create_group","name":name,"members":members})
    def mark_read(self,msg_id,sender): self.send_packet({"type":"msg_read","msg_id":msg_id,"original_sender":sender})
    def disconnect(self):
        self.connected=False
        try: self.sock.close()
        except: pass

# ══════════════════════════════════════════════════════════════════════════════
#  VOICE / VIDEO
# ══════════════════════════════════════════════════════════════════════════════
class VoiceEngine:
    def __init__(self):
        self.pa=None; self.si=None; self.so=None; self.available=False; self._cap=False
        try:
            import pyaudio; self.pa=pyaudio.PyAudio(); self.pyaudio=pyaudio; self.available=True
        except: pass
    def start_capture(self,cb):
        if not self.available: return
        self.si=self.pa.open(format=self.pyaudio.paInt16,channels=1,rate=16000,input=True,frames_per_buffer=1024)
        self._cap=True
        def _r():
            while self._cap:
                try: cb(base64.b64encode(self.si.read(1024,exception_on_overflow=False)).decode())
                except: break
        threading.Thread(target=_r,daemon=True).start()
    def stop_capture(self):
        self._cap=False
        try: self.si.stop_stream(); self.si.close()
        except: pass
    def play_chunk(self,b64):
        if not self.available: return
        try:
            if not self.so: self.so=self.pa.open(format=self.pyaudio.paInt16,channels=1,rate=16000,output=True)
            self.so.write(base64.b64decode(b64))
        except: pass
    def stop_playback(self):
        try: self.so.stop_stream(); self.so.close()
        except: pass
        self.so=None

class VideoEngine:
    def __init__(self):
        self.available=False; self.cap=None; self._cap=False
        try:
            import cv2,numpy
            from PIL import Image,ImageTk
            self.cv2=cv2; self.np=numpy; self.Image=Image; self.ImageTk=ImageTk; self.available=True
        except: pass
    def start_capture(self,cb):
        if not self.available: return False
        self.cap=self.cv2.VideoCapture(0)
        if not self.cap.isOpened(): return False
        self._cap=True
        def _r():
            while self._cap:
                ret,frame=self.cap.read()
                if not ret: break
                frame=self.cv2.resize(frame,(320,240))
                _,buf=self.cv2.imencode('.jpg',frame,[self.cv2.IMWRITE_JPEG_QUALITY,50])
                cb(base64.b64encode(buf.tobytes()).decode())
                time.sleep(0.033)
        threading.Thread(target=_r,daemon=True).start(); return True
    def stop_capture(self):
        self._cap=False
        try: self.cap.release()
        except: pass
    def decode_frame(self,b64):
        if not self.available: return None
        try:
            arr=self.np.frombuffer(base64.b64decode(b64),dtype=self.np.uint8)
            frame=self.cv2.imdecode(arr,self.cv2.IMREAD_COLOR)
            frame=self.cv2.cvtColor(frame,self.cv2.COLOR_BGR2RGB)
            return self.ImageTk.PhotoImage(image=self.Image.fromarray(frame))
        except: return None

# ══════════════════════════════════════════════════════════════════════════════
#  COLORS  (WhatsApp-like palette)
# ══════════════════════════════════════════════════════════════════════════════
# Left panel (chat list)
LP_BG      = "#111b21"
LP_HOVER   = "#202c33"
LP_SELECT  = "#2a3942"
LP_TOP     = "#202c33"
# Right panel (chat area)
RP_BG      = "#0b141a"
RP_TOP     = "#202c33"
RP_INPUT   = "#202c33"
RP_ENTRY   = "#2a3942"
# Bubbles
BUBBLE_ME  = "#005c4b"
BUBBLE_YOU = "#202c33"
# Text
TXT_W      = "#e9edef"
TXT_S      = "#8696a0"
TXT_T      = "#53bdeb"
# Accents
GREEN_WA   = "#00a884"
GREEN_LT   = "#25d366"
RED_WA     = "#f15c6d"
YELLOW_WA  = "#ffd279"
BLUE_WA    = "#53bdeb"
PURPLE_WA  = "#bf59cf"

F   = ("Segoe UI", 10)
FB  = ("Segoe UI", 10, "bold")
FS  = ("Segoe UI", 9)
FSS = ("Segoe UI", 8)
FT  = ("Segoe UI", 13, "bold")
FE  = ("Segoe UI Emoji", 15)

# ══════════════════════════════════════════════════════════════════════════════
#  INCOMING CALL POPUP
# ══════════════════════════════════════════════════════════════════════════════
class IncomingCallPopup:
    def __init__(self,parent,caller,call_id,call_type,on_accept,on_reject):
        self.win=tk.Toplevel(parent)
        icon="📹" if call_type=='video' else "📞"
        self.win.title(f"Incoming Call")
        self.win.geometry("340x200"); self.win.configure(bg=LP_TOP)
        self.win.resizable(False,False); self.win.attributes("-topmost",True)
        tk.Label(self.win,text=f"{icon}  Incoming {call_type.capitalize()} Call",
                 font=FB,bg=LP_TOP,fg=TXT_T).pack(pady=(24,6))
        tk.Label(self.win,text=caller,font=FT,bg=LP_TOP,fg=TXT_W).pack(pady=(0,20))
        bf=tk.Frame(self.win,bg=LP_TOP); bf.pack()
        tk.Button(bf,text="✅  Accept",font=FB,bg=GREEN_WA,fg="white",relief="flat",
                  cursor="hand2",padx=22,pady=10,
                  command=lambda:[on_accept(call_id,call_type),self.win.destroy()]).pack(side="left",padx=16)
        tk.Button(bf,text="❌  Decline",font=FB,bg=RED_WA,fg="white",relief="flat",
                  cursor="hand2",padx=22,pady=10,
                  command=lambda:[on_reject(call_id),self.win.destroy()]).pack(side="left",padx=16)

# ══════════════════════════════════════════════════════════════════════════════
#  VIDEO CALL WINDOW
# ══════════════════════════════════════════════════════════════════════════════
class VideoCallWindow:
    def __init__(self,parent,client,call_id,other,ve,vo):
        self.client=client; self.call_id=call_id; self.other=other
        self.ve=ve; self.vo=vo; self.active=True; self._muted=False; self._cam=True
        self.win=tk.Toplevel(parent)
        self.win.title(f"📹 {other}"); self.win.geometry("760,580".replace(",","x"))
        self.win.configure(bg="#000"); self.win.protocol("WM_DELETE_WINDOW",self._end)
        self._build(); self._start()

    def _build(self):
        top=tk.Frame(self.win,bg=LP_TOP,height=44); top.pack(fill="x"); top.pack_propagate(False)
        tk.Label(top,text=f"📹  {self.other}",font=FB,bg=LP_TOP,fg=TXT_W).pack(side="left",padx=14)
        self.timer_lbl=tk.Label(top,text="00:00",font=FB,bg=LP_TOP,fg=GREEN_WA)
        self.timer_lbl.pack(side="right",padx=14)
        self._t0=time.time(); self._tick()

        frm=tk.Frame(self.win,bg="#000"); frm.pack(fill="both",expand=True,padx=8,pady=8)
        rf=tk.Frame(frm,bg="#111"); rf.pack(side="left",expand=True,fill="both",padx=(0,4))
        tk.Label(rf,text=self.other,font=FSS,bg="#111",fg=TXT_S).pack(pady=2)
        self.remote_lbl=tk.Label(rf,bg="#000",text="Waiting for video...",fg=TXT_S,font=FS)
        self.remote_lbl.pack(expand=True,fill="both")

        lf=tk.Frame(frm,bg="#111",width=240); lf.pack(side="right",fill="y"); lf.pack_propagate(False)
        tk.Label(lf,text="You",font=FSS,bg="#111",fg=TXT_S).pack(pady=2)
        self.local_lbl=tk.Label(lf,bg="#000",text="Camera",fg=TXT_S,font=FS)
        self.local_lbl.pack(expand=True,fill="both")

        ctrl=tk.Frame(self.win,bg="#000"); ctrl.pack(pady=10)
        self.mute_btn=tk.Button(ctrl,text="🎙 Mute",font=FB,bg=LP_SELECT,fg=TXT_W,
                                relief="flat",cursor="hand2",padx=16,pady=8,command=self._mute)
        self.mute_btn.pack(side="left",padx=8)
        self.cam_btn=tk.Button(ctrl,text="📷 Cam Off",font=FB,bg=LP_SELECT,fg=TXT_W,
                               relief="flat",cursor="hand2",padx=16,pady=8,command=self._cam_toggle)
        self.cam_btn.pack(side="left",padx=8)
        tk.Button(ctrl,text="📵 End",font=FB,bg=RED_WA,fg="white",activebackground=RED_WA,
                  relief="flat",cursor="hand2",padx=16,pady=8,command=self._end).pack(side="left",padx=8)

    def _tick(self):
        if not self.active: return
        e=int(time.time()-self._t0); m,s=divmod(e,60)
        self.timer_lbl.config(text=f"{m:02d}:{s:02d}")
        self.win.after(1000,self._tick)

    def _start(self):
        if self.vo.available: self.vo.start_capture(lambda c:self.client.send_audio(self.call_id,c))
        if self.ve.available: self.ve.start_capture(lambda f:self.client.send_video(self.call_id,f))

    def update_remote_frame(self,b64):
        if not self.active: return
        photo=self.ve.decode_frame(b64)
        if photo: self.remote_lbl.config(image=photo,text=""); self.remote_lbl.image=photo

    def _mute(self):
        self._muted=not self._muted
        if self._muted: self.vo.stop_capture(); self.mute_btn.config(text="🔇 Unmute",bg=RED_WA)
        else: self.vo.start_capture(lambda c:self.client.send_audio(self.call_id,c)); self.mute_btn.config(text="🎙 Mute",bg=LP_SELECT)

    def _cam_toggle(self):
        self._cam=not self._cam
        if not self._cam: self.ve.stop_capture(); self.local_lbl.config(image="",text="Camera Off"); self.cam_btn.config(text="📷 Cam On",bg=RED_WA)
        else: self.ve.start_capture(lambda f:self.client.send_video(self.call_id,f)); self.cam_btn.config(text="📷 Cam Off",bg=LP_SELECT)

    def _end(self):
        self.active=False; self.ve.stop_capture(); self.vo.stop_capture(); self.vo.stop_playback()
        self.client.call_end(self.call_id)
        try: self.win.destroy()
        except: pass

    def on_call_ended(self):
        self.active=False; self.ve.stop_capture(); self.vo.stop_capture(); self.vo.stop_playback()
        try: self.win.destroy()
        except: pass

# ══════════════════════════════════════════════════════════════════════════════
#  EMOJI PICKER
# ══════════════════════════════════════════════════════════════════════════════
class EmojiPicker:
    EMOJIS=["😀","😂","😍","😎","😭","😡","🥳","😴","🤔","😱",
            "👍","👎","❤️","🔥","⭐","🎉","🙏","💪","🤝","👏",
            "😊","🥰","😘","😜","🤣","😢","😤","🤯","🥺","😇",
            "🍕","🍔","🎮","⚽","🎵","🚀","💻","📱","🎂","🌟"]
    def __init__(self,parent,cb):
        w=tk.Toplevel(parent); w.title(""); w.geometry("340,210".replace(",","x"))
        w.configure(bg=LP_TOP); w.attributes("-topmost",True); w.resizable(False,False)
        col=row=0
        for e in self.EMOJIS:
            tk.Button(w,text=e,font=("Segoe UI Emoji",14),bg=LP_TOP,
                      activebackground=LP_SELECT,relief="flat",cursor="hand2",bd=0,
                      command=lambda x=e:[cb(x),w.destroy()]).grid(row=row,column=col,padx=2,pady=2)
            col+=1
            if col>9: col=0; row+=1

# ══════════════════════════════════════════════════════════════════════════════
#  LOGIN WINDOW
# ══════════════════════════════════════════════════════════════════════════════
class LoginWindow:
    def __init__(self,root):
        self.root=root; self.root.title("ChatNet")
        self.root.geometry("400,580".replace(",","x"))
        self.root.configure(bg=RP_BG); self.root.resizable(True,True)
        self._build()

    def _build(self):
        tk.Label(self.root,text="ChatNet",font=("Segoe UI",26,"bold"),
                 bg=RP_BG,fg=GREEN_WA).pack(pady=(30,4))
        tk.Label(self.root,text="Simple. Secure. Reliable.",
                 font=FS,bg=RP_BG,fg=TXT_S).pack(pady=(0,24))

        frm=tk.Frame(self.root,bg=LP_TOP,padx=24,pady=20); frm.pack(padx=24,fill="x")

        def field(lbl,default="",show=None):
            tk.Label(frm,text=lbl,font=FSS,bg=LP_TOP,fg=TXT_S,anchor="w").pack(fill="x",pady=(8,2))
            e=tk.Entry(frm,font=F,bg=LP_SELECT,fg=TXT_W,insertbackground=GREEN_WA,
                       relief="flat",show=show or "",highlightthickness=1,
                       highlightcolor=GREEN_WA,highlightbackground=LP_SELECT)
            e.pack(fill="x",ipady=8); e.insert(0,default); return e

        self.host_e=field("SERVER HOST","127.0.0.1")
        self.port_e=field("PORT","9090")
        self.user_e=field("YOUR NAME")
        self.pass_e=field("PASSWORD",show="●")
        self.room_e=field("ROOM","General")
        self.about_e=field("ABOUT","Hey there! I am using ChatNet")

        tk.Button(frm,text="LOGIN",font=FB,bg=GREEN_WA,fg="white",
                  activebackground=GREEN_LT,relief="flat",cursor="hand2",
                  pady=10,command=lambda:self._auth('login')).pack(fill="x",pady=(16,4))
        tk.Button(frm,text="NEW ACCOUNT",font=FB,bg=LP_SELECT,fg=TXT_W,
                  activebackground=LP_HOVER,relief="flat",cursor="hand2",
                  pady=10,command=lambda:self._auth('register')).pack(fill="x")

        self.status=tk.Label(self.root,text="",font=FSS,bg=RP_BG,fg=RED_WA)
        self.status.pack(pady=6)

    def _auth(self,action):
        host=self.host_e.get().strip(); port=self.port_e.get().strip()
        user=self.user_e.get().strip(); pw=self.pass_e.get()
        room=self.room_e.get().strip() or "General"
        about=self.about_e.get().strip()
        if not host or not user or not pw: self.status.config(text="All fields required"); return
        self.status.config(text="Connecting..."); self.root.update()
        def _go():
            try:
                c=ChatClient(host,port,lambda p:None); c.connect()
                ok,reason=c.authenticate(user,pw,action,about)
                if not ok: self.status.config(text=f"Error: {reason}"); return
                if not c.join_room(room): self.status.config(text="Could not join room"); return
                self.root.after(0,lambda:self._open(c,user,room))
            except Exception as e: self.status.config(text=f"Error: {e}")
        threading.Thread(target=_go,daemon=True).start()

    def _open(self,client,username,room):
        self.root.withdraw()
        w=tk.Toplevel(self.root)
        w.protocol("WM_DELETE_WINDOW",lambda:[client.disconnect(),w.destroy(),self.root.destroy()])
        App(w,client,username,room)

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APP  — WhatsApp Layout
# ══════════════════════════════════════════════════════════════════════════════
class App:
    def __init__(self,root,client,username,room):
        self.root=root; self.client=client
        self.username=username; self.current_room=room
        self.private_to=None; self.reply_to=None
        self.current_call_id=None; self.video_win=None
        self.voice=VoiceEngine(); self.video=VideoEngine()
        self.typing_timer=None; self.typing_users=set()
        self.online_users=[]; self.user_info={}
        self.chat_messages={}   # room/dm -> list of messages
        self.chat_list=[]       # left panel entries
        self.unread={}          # room/dm -> count

        self.root.title("ChatNet")
        self.root.geometry("1280,720".replace(",","x"))
        self.root.configure(bg=LP_BG)
        self.root.minsize(900,600)
        self._build()
        client.on_packet=self._on_packet
        client.start_listener(); client.get_users()

    # ─────────────────────────────────────────────────────────────────────────
    #  BUILD UI
    # ─────────────────────────────────────────────────────────────────────────
    def _build(self):
        # ── ROOT: left(320) + right(expand) ──────────────────────────────────
        self.left=tk.Frame(self.root,bg=LP_BG,width=320)
        self.left.pack(side="left",fill="y"); self.left.pack_propagate(False)

        # thin separator
        tk.Frame(self.root,bg="#1f2c33",width=1).pack(side="left",fill="y")

        self.right=tk.Frame(self.root,bg=RP_BG)
        self.right.pack(side="left",fill="both",expand=True)

        self._build_left()
        self._build_right()

    # ── LEFT PANEL ────────────────────────────────────────────────────────────
    def _build_left(self):
        # top bar
        ltop=tk.Frame(self.left,bg=LP_TOP,height=56)
        ltop.pack(fill="x"); ltop.pack_propagate(False)

        # avatar circle
        av=tk.Label(ltop,text=self.username[0].upper(),font=FB,
                    bg=GREEN_WA,fg="white",width=3,height=1,relief="flat")
        av.pack(side="left",padx=(14,8),pady=10)

        tk.Label(ltop,text=self.username,font=FB,bg=LP_TOP,fg=TXT_W).pack(side="left")

        # icons right side
        icon_frm=tk.Frame(ltop,bg=LP_TOP); icon_frm.pack(side="right",padx=8)
        for txt,cmd in [("👥",self._new_group),("🔍",self._open_search),("⋮",self._show_menu)]:
            tk.Button(icon_frm,text=txt,font=FE,bg=LP_TOP,fg=TXT_S,
                      activebackground=LP_HOVER,relief="flat",cursor="hand2",bd=0,
                      command=cmd).pack(side="left",padx=4)

        # search bar
        sfrm=tk.Frame(self.left,bg=LP_BG,pady=6); sfrm.pack(fill="x",padx=8)
        self.search_var=tk.StringVar()
        self.search_var.trace('w',self._filter_chats)
        se=tk.Entry(sfrm,textvariable=self.search_var,font=FS,bg=LP_SELECT,fg=TXT_W,
                    insertbackground=GREEN_WA,relief="flat",
                    highlightthickness=0)
        se.pack(fill="x",ipady=7,padx=4)
        tk.Label(sfrm,text="🔍",font=FSS,bg=LP_BG,fg=TXT_S).place(in_=se,relx=0.97,rely=0.5,anchor="e")

        # status filter tabs
        tabs=tk.Frame(self.left,bg=LP_BG); tabs.pack(fill="x",padx=8,pady=(0,4))
        self.tab_var=tk.StringVar(value="All")
        for t in ["All","Groups","DMs"]:
            tk.Radiobutton(tabs,text=t,variable=self.tab_var,value=t,font=FSS,
                           bg=LP_BG,fg=TXT_S,selectcolor=LP_SELECT,
                           activebackground=LP_BG,indicatoron=False,
                           relief="flat",padx=10,pady=4,cursor="hand2",
                           command=self._filter_chats).pack(side="left",padx=2)

        # chat list
        list_frm=tk.Frame(self.left,bg=LP_BG); list_frm.pack(fill="both",expand=True)
        self.chat_canvas=tk.Canvas(list_frm,bg=LP_BG,highlightthickness=0)
        sb=tk.Scrollbar(list_frm,orient="vertical",command=self.chat_canvas.yview)
        self.chat_canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right",fill="y")
        self.chat_canvas.pack(side="left",fill="both",expand=True)
        self.chat_list_frame=tk.Frame(self.chat_canvas,bg=LP_BG)
        self.chat_canvas.create_window((0,0),window=self.chat_list_frame,anchor="nw")
        self.chat_list_frame.bind("<Configure>",lambda e:self.chat_canvas.configure(
            scrollregion=self.chat_canvas.bbox("all")))

    # ── RIGHT PANEL ───────────────────────────────────────────────────────────
    def _build_right(self):
        # placeholder when no chat selected
        self.placeholder=tk.Frame(self.right,bg=RP_BG)
        self.placeholder.place(relx=0,rely=0,relwidth=1,relheight=1)
        tk.Label(self.placeholder,text="💬",font=("Segoe UI Emoji",52),
                 bg=RP_BG,fg=TXT_S).pack(expand=True)
        tk.Label(self.placeholder,text="ChatNet",font=FT,bg=RP_BG,fg=TXT_W).pack()
        tk.Label(self.placeholder,text="Click a chat on the left to start messaging",
                 font=FS,bg=RP_BG,fg=TXT_S).pack(pady=4)

        # actual chat panel (hidden until a chat is selected)
        self.chat_panel=tk.Frame(self.right,bg=RP_BG)

        # top bar
        self.rtop=tk.Frame(self.chat_panel,bg=RP_TOP,height=56)
        self.rtop.pack(fill="x"); self.rtop.pack_propagate(False)

        self.peer_av=tk.Label(self.rtop,text="?",font=FB,bg=GREEN_WA,
                              fg="white",width=3,height=1)
        self.peer_av.pack(side="left",padx=(14,8),pady=10)

        info_frm=tk.Frame(self.rtop,bg=RP_TOP); info_frm.pack(side="left")
        self.peer_name=tk.Label(info_frm,text="",font=FB,bg=RP_TOP,fg=TXT_W)
        self.peer_name.pack(anchor="w")
        self.peer_status=tk.Label(info_frm,text="",font=FSS,bg=RP_TOP,fg=GREEN_WA)
        self.peer_status.pack(anchor="w")

        # top right icons
        tright=tk.Frame(self.rtop,bg=RP_TOP); tright.pack(side="right",padx=8)
        tk.Button(tright,text="📹",font=FE,bg=RP_TOP,fg=TXT_S,
                  activebackground=LP_HOVER,relief="flat",cursor="hand2",bd=0,
                  command=lambda:self._start_call('video')).pack(side="left",padx=6)
        tk.Button(tright,text="📞",font=FE,bg=RP_TOP,fg=TXT_S,
                  activebackground=LP_HOVER,relief="flat",cursor="hand2",bd=0,
                  command=lambda:self._start_call('voice')).pack(side="left",padx=6)
        tk.Button(tright,text="🔍",font=FE,bg=RP_TOP,fg=TXT_S,
                  activebackground=LP_HOVER,relief="flat",cursor="hand2",bd=0,
                  command=self._open_search).pack(side="left",padx=6)

        self.call_lbl=tk.Label(self.rtop,text="",font=FSS,bg=RP_TOP,fg=GREEN_WA)
        self.call_lbl.pack(side="left",padx=8)

        # chat messages area
        self.msg_canvas=tk.Canvas(self.chat_panel,bg=RP_BG,highlightthickness=0)
        msg_sb=tk.Scrollbar(self.chat_panel,orient="vertical",command=self.msg_canvas.yview)
        self.msg_canvas.configure(yscrollcommand=msg_sb.set)
        msg_sb.pack(side="right",fill="y")
        self.msg_canvas.pack(fill="both",expand=True)
        self.msg_frame=tk.Frame(self.msg_canvas,bg=RP_BG)
        self._msg_win=self.msg_canvas.create_window((0,0),window=self.msg_frame,anchor="nw")
        self.msg_frame.bind("<Configure>",lambda e:self.msg_canvas.configure(
            scrollregion=self.msg_canvas.bbox("all")))
        # CRITICAL: make msg_frame width = canvas width so right-align works
        self.msg_canvas.bind("<Configure>",lambda e:self.msg_canvas.itemconfig(
            self._msg_win, width=e.width))

        # typing label
        self.typing_lbl=tk.Label(self.chat_panel,text="",font=FSS,bg=RP_BG,fg=GREEN_WA)
        self.typing_lbl.pack(anchor="w",padx=16)

        # reply bar
        self.reply_bar=tk.Frame(self.chat_panel,bg=LP_SELECT)
        self.reply_icon=tk.Label(self.reply_bar,text="↩",font=FB,bg=LP_SELECT,fg=GREEN_WA)
        self.reply_icon.pack(side="left",padx=8)
        self.reply_lbl=tk.Label(self.reply_bar,text="",font=FSS,bg=LP_SELECT,
                                fg=TXT_S,anchor="w")
        self.reply_lbl.pack(side="left",fill="x",expand=True)
        tk.Button(self.reply_bar,text="✖",font=FSS,bg=LP_SELECT,fg=RED_WA,
                  relief="flat",cursor="hand2",command=self._clear_reply).pack(side="right",padx=6)

        # reaction bar
        rbar=tk.Frame(self.chat_panel,bg=RP_INPUT)
        rbar.pack(fill="x")
        tk.Label(rbar,text="React:",font=FSS,bg=RP_INPUT,fg=TXT_S).pack(side="left",padx=(12,6))
        self._react_btns = {}
        for emoji,color in [("👍","#f59e0b"),("❤️","#ef4444"),("😂","#facc15"),
                             ("😮","#fb923c"),("🔥","#f97316"),("👏","#a3e635"),
                             ("🎉","#c084fc"),("😢","#60a5fa")]:
            btn=tk.Button(rbar,text=emoji,font=("Segoe UI Emoji",16),bg=RP_INPUT,
                      activebackground=color,relief="flat",cursor="hand2",bd=0,
                      padx=6,pady=4,
                      command=lambda e=emoji,c=color:self._send_reaction(e,c))
            btn.pack(side="left",padx=2,pady=3)
            self._react_btns[emoji]=btn

        # input bar
        ibar=tk.Frame(self.chat_panel,bg=RP_INPUT,pady=8)
        ibar.pack(fill="x",padx=0)

        tk.Button(ibar,text="😀",font=("Segoe UI Emoji",15),bg=RP_INPUT,fg=TXT_S,
                  activebackground=LP_HOVER,relief="flat",cursor="hand2",bd=0,
                  command=self._open_emoji).pack(side="left",padx=(12,4))

        self.msg_var=tk.StringVar()
        self.msg_e=tk.Entry(ibar,textvariable=self.msg_var,font=F,bg=RP_ENTRY,
                            fg=TXT_W,insertbackground=GREEN_WA,relief="flat",
                            highlightthickness=0)
        self.msg_e.pack(side="left",fill="both",expand=True,ipady=10,padx=8)
        self.msg_e.bind("<Return>",self._send_msg)
        self.msg_e.bind("<KeyRelease>",self._on_key)

        self.attach_btn=tk.Button(ibar,text="📎",font=("Segoe UI Emoji",15),bg=RP_INPUT,fg=TXT_S,
                  activebackground=LP_HOVER,relief="flat",cursor="hand2",bd=0,
                  command=self._open_attach_menu)
        self.attach_btn.pack(side="left",padx=4)

        self.send_btn=tk.Button(ibar,text="➤",font=FB,bg=GREEN_WA,fg="white",
                                activebackground=GREEN_LT,relief="flat",cursor="hand2",
                                padx=12,pady=6,command=self._send_msg)
        self.send_btn.pack(side="left",padx=(0,12))

    # ─────────────────────────────────────────────────────────────────────────
    #  CHAT LIST (left panel)
    # ─────────────────────────────────────────────────────────────────────────
    def _add_chat_entry(self,name,subtitle="",is_group=False,unread=0):
        # remove if already exists
        for w in self.chat_list_frame.winfo_children():
            if getattr(w,'_chat_name',None)==name: w.destroy()

        row=tk.Frame(self.chat_list_frame,bg=LP_BG,cursor="hand2")
        row._chat_name=name
        row.pack(fill="x")

        # hover effects
        def _enter(e): row.config(bg=LP_HOVER); [c.config(bg=LP_HOVER) for c in row.winfo_children() if hasattr(c,'config')]
        def _leave(e):
            col=LP_SELECT if name==self.private_to or (not self.private_to and name==self.current_room) else LP_BG
            row.config(bg=col); [c.config(bg=col) for c in row.winfo_children() if hasattr(c,'config')]
        row.bind("<Enter>",_enter); row.bind("<Leave>",_leave)
        row.bind("<Button-1>",lambda e:self._select_chat(name,is_group))

        # avatar
        av_color=PURPLE_WA if is_group else GREEN_WA
        av_text="👥" if is_group else name[0].upper()
        av_font=("Segoe UI Emoji",12) if is_group else FB
        av=tk.Label(row,text=av_text,font=av_font,bg=av_color,fg="white",width=3,height=1)
        av.pack(side="left",padx=(12,10),pady=8)
        av.bind("<Button-1>",lambda e:self._select_chat(name,is_group))

        info=tk.Frame(row,bg=LP_BG); info.pack(side="left",fill="x",expand=True)
        info.bind("<Button-1>",lambda e:self._select_chat(name,is_group))

        top_row=tk.Frame(info,bg=LP_BG); top_row.pack(fill="x")
        top_row.bind("<Button-1>",lambda e:self._select_chat(name,is_group))
        tk.Label(top_row,text=name,font=FB,bg=LP_BG,fg=TXT_W,anchor="w").pack(side="left")

        now=datetime.datetime.now().strftime("%H:%M")
        tk.Label(top_row,text=now,font=FSS,bg=LP_BG,fg=TXT_S).pack(side="right",padx=8)

        sub_row=tk.Frame(info,bg=LP_BG); sub_row.pack(fill="x")
        sub_row.bind("<Button-1>",lambda e:self._select_chat(name,is_group))
        sub_lbl=tk.Label(sub_row,text=subtitle[:40] if subtitle else ("Group chat" if is_group else "Click to chat"),
                         font=FSS,bg=LP_BG,fg=TXT_S,anchor="w")
        sub_lbl.pack(side="left",fill="x",expand=True)

        if unread>0:
            tk.Label(sub_row,text=str(unread),font=FSS,bg=GREEN_WA,fg="white",
                     padx=6,pady=1).pack(side="right",padx=8)

        sep=tk.Frame(self.chat_list_frame,bg="#1f2c33",height=1)
        sep.pack(fill="x",padx=12)

    def _select_chat(self,name,is_group=False):
        self.private_to=None if is_group or name==self.current_room else name
        self.unread[name]=0

        # show chat panel
        self.placeholder.place_forget()
        self.chat_panel.place(relx=0,rely=0,relwidth=1,relheight=1)

        # update top bar
        info=self.user_info.get(name,{})
        status=info.get('status','online') if not is_group else 'group'
        self.peer_name.config(text=name)
        self.peer_av.config(text="👥" if is_group else name[0].upper(),
                            bg=PURPLE_WA if is_group else GREEN_WA,
                            font=("Segoe UI Emoji",12) if is_group else FB)
        if is_group:
            self.peer_status.config(text="Group Chat",fg=TXT_S)
        else:
            color=GREEN_WA if status=='online' else YELLOW_WA if status=='away' else RED_WA if status=='busy' else TXT_S
            self.peer_status.config(text=f"● {status}",fg=color)

        # load messages for this chat
        self._render_messages(name)

        # highlight selected in list
        for w in self.chat_list_frame.winfo_children():
            if hasattr(w,'_chat_name'):
                col=LP_SELECT if w._chat_name==name else LP_BG
                try: w.config(bg=col)
                except: pass

    def _filter_chats(self,*args):
        q=self.search_var.get().lower(); tab=self.tab_var.get()
        for w in self.chat_list_frame.winfo_children():
            if not hasattr(w,'_chat_name'): continue
            name=w._chat_name
            is_group=name in [e.get('name','') for e in self.chat_list if e.get('is_group')]
            show=True
            if q and q not in name.lower(): show=False
            if tab=="Groups" and not is_group: show=False
            if tab=="DMs" and is_group: show=False
            w.pack(fill="x") if show else w.pack_forget()

    # ─────────────────────────────────────────────────────────────────────────
    #  MESSAGE RENDERING
    # ─────────────────────────────────────────────────────────────────────────
    def _render_messages(self,chat_key):
        for w in self.msg_frame.winfo_children(): w.destroy()
        msgs=self.chat_messages.get(chat_key,[])
        for m in msgs: self._render_bubble(m)
        self.msg_canvas.update_idletasks()
        self.msg_canvas.yview_moveto(1.0)

    def _render_bubble(self,pkt):
        t=pkt.get('type','message')
        if t=='system':
            sys_frm=tk.Frame(self.msg_frame,bg=RP_BG)
            sys_frm.pack(fill="x",pady=2)
            tk.Label(sys_frm,text=pkt.get('text',''),font=FSS,
                     bg="#182229",fg=TXT_S,padx=14,pady=3).pack()
            return
        if t=='reaction_display':
            sender=pkt.get('from','?'); emoji=pkt.get('emoji','👍')
            is_self = sender==self.username
            frm=tk.Frame(self.msg_frame,bg=RP_BG)
            frm.pack(fill="x",padx=12,pady=1)
            frm.columnconfigure(0,weight=1)
            inner=tk.Frame(frm,bg="#1a2a1a",padx=10,pady=4)
            inner.grid(row=0,column=0,sticky="e" if is_self else "w",
                       padx=(60 if is_self else 0, 0 if is_self else 60))
            tk.Label(inner,text=emoji,font=("Segoe UI Emoji",20),
                     bg="#1a2a1a",fg=TXT_W).pack(side="left",padx=(0,6))
            lbl="You reacted" if is_self else f"{sender} reacted"
            tk.Label(inner,text=lbl,font=FSS,bg="#1a2a1a",fg=GREEN_WA).pack(side="left")
            return
        if t not in ('message','file'): return

        sender=pkt.get('from','?'); is_self=sender==self.username
        text=pkt.get('text',''); ts=pkt.get('time','')
        reply_to=pkt.get('reply_to')

        # outer row — full width
        outer=tk.Frame(self.msg_frame,bg=RP_BG)
        outer.pack(fill="x",padx=8,pady=3)
        outer.columnconfigure(0,weight=1)

        bubble_color=BUBBLE_ME if is_self else BUBBLE_YOU

        # bubble frame — placed LEFT or RIGHT using grid
        bubble=tk.Frame(outer,bg=bubble_color,padx=12,pady=8)
        if is_self:
            # MY messages: stick to RIGHT side
            bubble.grid(row=0,column=0,sticky="e",padx=(80,4))
        else:
            # THEIR messages: stick to LEFT side
            bubble.grid(row=0,column=0,sticky="w",padx=(4,80))

        # sender name (only for others in group)
        if not is_self:
            tk.Label(bubble,text=sender,font=("Segoe UI",9,"bold"),
                     bg=bubble_color,fg=GREEN_WA,anchor="w").pack(anchor="w")

        # reply quote
        if reply_to:
            q=tk.Frame(bubble,bg="#0d2438" if is_self else "#0a1a24",padx=8,pady=4)
            q.pack(fill="x",pady=(0,6))
            tk.Label(q,text=f"↩  {str(reply_to)[:45]}",font=FSS,
                     bg="#0d2438" if is_self else "#0a1a24",fg=TXT_S).pack(anchor="w")

        # content
        if t=='file':
            fname=pkt.get('filename','file'); sz=pkt.get('size',0)
            ftype=pkt.get('file_type','other')
            saved=pkt.get('_saved_path','')

            def _open_file(p):
                if os.name=='nt':
                    os.startfile(p)
                else:
                    os.system(f"xdg-open '{p}'")

            if ftype=='image' and saved and os.path.exists(saved):
                # ── IMAGE: show thumbnail, click to open full size ──────────
                try:
                    from PIL import Image, ImageTk
                    img=Image.open(saved)
                    img.thumbnail((300,220))
                    photo=ImageTk.PhotoImage(img)
                    img_lbl=tk.Label(bubble,image=photo,bg=bubble_color,
                                     cursor="hand2",relief="flat")
                    img_lbl.image=photo
                    img_lbl.pack(anchor="w",pady=(0,2))
                    img_lbl.bind("<Button-1>",lambda e,p=saved:_open_file(p))
                    # caption row
                    cap=tk.Frame(bubble,bg=bubble_color); cap.pack(fill="x")
                    tk.Label(cap,text=fname,font=FSS,bg=bubble_color,
                             fg=TXT_S,anchor="w").pack(side="left")
                    tk.Label(cap,text=self._fmt(sz),font=FSS,bg=bubble_color,
                             fg=TXT_S).pack(side="right")
                except Exception as ex:
                    self._file_doc_bubble(bubble,bubble_color,"🖼",fname,sz,saved,_open_file)

            elif ftype=='audio' and saved and os.path.exists(saved):
                # ── AUDIO: waveform bar + play button ───────────────────────
                import random; random.seed(abs(hash(fname))%9999)
                af=tk.Frame(bubble,bg="#0b1f2e",padx=10,pady=10,cursor="hand2")
                af.pack(fill="x",pady=(0,4))
                af.bind("<Button-1>",lambda e,p=saved:self._open_path(p))

                left=tk.Frame(af,bg="#0b1f2e"); left.pack(side="left")
                play_btn=tk.Button(left,text="▶",font=("Segoe UI",14,"bold"),
                                   bg=GREEN_WA,fg="white",relief="flat",
                                   cursor="hand2",width=2,
                                   command=lambda p=saved:_open_file(p))
                play_btn.pack()

                mid=tk.Frame(af,bg="#0b1f2e"); mid.pack(side="left",padx=10,fill="x",expand=True)
                tk.Label(mid,text=fname,font=FB,bg="#0b1f2e",
                         fg=TXT_W,anchor="w").pack(anchor="w")
                # waveform
                wf=tk.Frame(mid,bg="#0b1f2e"); wf.pack(anchor="w",pady=(4,2))
                for _ in range(22):
                    h=random.randint(4,20)
                    c=GREEN_WA if random.random()>0.4 else "#1a5c4a"
                    tk.Frame(wf,bg=c,width=3,height=h).pack(side="left",padx=1)
                tk.Label(mid,text=self._fmt(sz),font=FSS,bg="#0b1f2e",
                         fg=TXT_S,anchor="w").pack(anchor="w")

            elif ftype=='video' and saved and os.path.exists(saved):
                # ── VIDEO: dark preview box + open button ───────────────────
                vf=tk.Frame(bubble,bg="#000",width=300,height=170,cursor="hand2")
                vf.pack(pady=(0,4)); vf.pack_propagate(False)
                vf.bind("<Button-1>",lambda e,p=saved:self._open_path(p))
                tk.Label(vf,text="▶",font=("Segoe UI",40,"bold"),
                         bg="#000",fg="white",cursor="hand2").pack(expand=True)
                tk.Label(vf,text=fname,font=FSS,bg="#000",fg=TXT_S).pack(pady=(0,4))
                cap=tk.Frame(bubble,bg=bubble_color); cap.pack(fill="x")
                tk.Label(cap,text="🎥  "+fname,font=FSS,bg=bubble_color,
                         fg=TXT_S,anchor="w").pack(side="left")
                tk.Label(cap,text=self._fmt(sz),font=FSS,bg=bubble_color,
                         fg=TXT_S).pack(side="right")

            else:
                # ── DOCUMENT / ZIP / OTHER ───────────────────────────────────
                self._file_doc_bubble(bubble,bubble_color,
                    "📄",fname,sz,saved,_open_file)

        elif text.startswith("📍"):
            # Location message — show as WhatsApp location card
            lines=text.split("|")
            loc_name=lines[0].replace("📍 Location:","").strip() if lines else text
            maps_url=""
            for part in lines:
                if "maps.google" in part:
                    maps_url=part.replace("Maps:","").strip()

            loc_card=tk.Frame(bubble,bg="#0d2438",padx=0,pady=0)
            loc_card.pack(fill="x",pady=(0,4))

            # map image placeholder
            map_bg=tk.Frame(loc_card,bg="#1a3a2a",height=120,width=280)
            map_bg.pack(fill="x"); map_bg.pack_propagate(False)
            tk.Label(map_bg,text="🗺",font=("Segoe UI Emoji",40),
                     bg="#1a3a2a",fg=GREEN_WA).pack(expand=True)

            # location details
            details=tk.Frame(loc_card,bg="#0d2438",padx=10,pady=8)
            details.pack(fill="x")
            tk.Label(details,text="📍  "+loc_name,font=FB,
                     bg="#0d2438",fg=TXT_W,anchor="w",wraplength=260).pack(anchor="w")
            if maps_url:
                tk.Button(details,text="Open in Google Maps  →",font=FSS,
                          bg=GREEN_WA,fg="white",relief="flat",cursor="hand2",
                          pady=4,padx=8,
                          command=lambda u=maps_url:__import__('webbrowser').open(u)
                          ).pack(anchor="w",pady=(6,0))

        elif text.startswith("👤"):
            # Contact card
            lines=text.split("|")
            contact_card=tk.Frame(bubble,bg="#0d2438",padx=12,pady=10)
            contact_card.pack(fill="x",pady=(0,4))
            tk.Label(contact_card,text="👤",font=("Segoe UI Emoji",28),
                     bg="#0d2438",fg=GREEN_WA).pack(side="left",padx=(0,12))
            info=tk.Frame(contact_card,bg="#0d2438"); info.pack(side="left",fill="x",expand=True)
            for line in lines:
                if line.strip():
                    tk.Label(info,text=line.strip(),font=FS if "Contact:" in line else FSS,
                             bg="#0d2438",fg=TXT_W if "Contact:" in line else TXT_S,
                             anchor="w").pack(anchor="w")

        else:
            tk.Label(bubble,text=text,font=F,bg=bubble_color,fg=TXT_W,
                     wraplength=420,justify="left",anchor="w").pack(anchor="w")

        # footer: time + tick
        foot=tk.Frame(bubble,bg=bubble_color)
        foot.pack(anchor="e",pady=(4,0))
        tk.Label(foot,text=ts,font=FSS,bg=bubble_color,fg=TXT_S).pack(side="left")
        if is_self:
            tk.Label(foot,text="  ✓✓",font=FSS,bg=bubble_color,fg=GREEN_WA).pack(side="left")

        # right-click menu
        for w in [bubble]+bubble.winfo_children():
            try: w.bind("<Button-3>",lambda e,p=pkt:self._bubble_menu(e,p))
            except: pass

    def _bubble_menu(self,event,pkt):
        menu=tk.Menu(self.root,tearoff=0,bg=LP_SELECT,fg=TXT_W,
                     activebackground=LP_HOVER,font=FS)
        text=pkt.get('text','')
        menu.add_command(label="↩  Reply",command=lambda:self._set_reply(text))
        menu.add_command(label="↪  Forward",command=lambda:self._forward(pkt))
        menu.add_command(label="📋  Copy",command=lambda:self._copy_text(text))
        menu.add_separator()
        menu.add_command(label="🗑  Delete",command=lambda:self.client.delete_message(pkt.get('msg_id','')))
        try: menu.tk_popup(event.x_root,event.y_root)
        finally: menu.grab_release()

    def _add_msg(self,chat_key,pkt):
        self.chat_messages.setdefault(chat_key,[]).append(pkt)
        # determine active chat
        active=self.private_to or self.current_room
        if chat_key==active:
            self._render_bubble(pkt)
            self.msg_canvas.update_idletasks()
            self.msg_canvas.yview_moveto(1.0)
        else:
            self.unread[chat_key]=self.unread.get(chat_key,0)+1

    # ─────────────────────────────────────────────────────────────────────────
    #  PACKET DISPATCH
    # ─────────────────────────────────────────────────────────────────────────
    def _on_packet(self,pkt):
        self.root.after(0,lambda:self._dispatch(pkt))

    def _dispatch(self,pkt):
        t=pkt.get('type')
        if   t=='message':         self._on_message(pkt)
        elif t=='file':            self._on_file(pkt)
        elif t=='system':          self._on_system(pkt)
        elif t=='user_list':       self._on_user_list(pkt)
        elif t=='message_history': self._on_history(pkt)
        elif t=='typing':          self._on_typing(pkt.get('from',''))
        elif t=='stop_typing':     self._stop_typing(pkt.get('from',''))
        elif t=='reaction':        self._on_reaction(pkt)
        elif t=='reaction_display': pass  # already handled in _add_msg → _render_bubble
        elif t=='message_deleted': self._on_deleted(pkt)
        elif t=='msg_read':        self._on_read(pkt)
        elif t=='user_status':     self._on_status(pkt)
        elif t=='user_joined':     self._on_joined(pkt)
        elif t=='user_left':       self._on_left(pkt)
        elif t=='added_to_group':  self._on_added_group(pkt)
        elif t=='incoming_call':   self._on_incoming_call(pkt)
        elif t=='call_ringing':    self._on_ringing(pkt)
        elif t=='call_accepted':   self._on_call_accepted(pkt)
        elif t=='call_rejected':   self._on_call_rejected(pkt)
        elif t=='call_ended':      self._on_call_ended(pkt)
        elif t=='audio_chunk':     self.voice.play_chunk(pkt.get('audio',''))
        elif t=='video_chunk':
            if self.video_win: self.video_win.update_remote_frame(pkt.get('frame',''))
        elif t in ('disconnected','error'):
            self._add_msg(self.current_room,{"type":"system","text":"⚠ Disconnected"})

    # ─────────────────────────────────────────────────────────────────────────
    #  MESSAGE HANDLERS
    # ─────────────────────────────────────────────────────────────────────────
    def _on_message(self,pkt):
        sender=pkt.get('from','?'); private=pkt.get('private',False)
        is_self=sender==self.username
        chat_key=self.private_to if (private and is_self) else \
                 sender if private else self.current_room
        self._add_msg(chat_key,pkt)
        if not is_self:
            # update chat list preview
            self._add_chat_entry(sender,pkt.get('text',''),False,
                                 self.unread.get(sender,0))
            self._flash_title(chat_key)
            self.client.mark_read(pkt.get('msg_id',''),sender)

    def _on_file(self,pkt):
        sender=pkt.get('from','?'); private=pkt.get('private',False)
        is_self=sender==self.username
        chat_key=self.private_to if (private and is_self) else \
                 sender if private else self.current_room
        path=self.client.save_file(pkt)
        pkt['_saved_path']=path
        self._add_msg(chat_key,pkt)
        if not is_self: self._flash_title(chat_key)

    def _on_system(self,pkt):
        self._add_msg(self.current_room,pkt)
        self._add_chat_entry(self.current_room,pkt.get('text',''))

    def _on_history(self,pkt):
        msgs=pkt.get('messages',[])
        for m in msgs:
            t=m.get('type')
            if t in ('message','file','system'):
                self.chat_messages.setdefault(self.current_room,[]).append(m)
        active=self.private_to or self.current_room
        if active==self.current_room:
            self._render_messages(self.current_room)

    def _on_user_list(self,pkt):
        users=pkt.get('users',[]); self.online_users=users
        for ui in pkt.get('user_info',[]):
            self.user_info[ui['username']]=ui
        # rebuild chat list
        for w in self.chat_list_frame.winfo_children(): w.destroy()
        # add current room first
        self._add_chat_entry(self.current_room,"",False)
        # add each online user as DM
        for u in users:
            if u!=self.username:
                self._add_chat_entry(u,"",False,self.unread.get(u,0))

    def _on_reaction(self,pkt):
        sender=pkt.get('from','?'); emoji=pkt.get('emoji','👍')
        chat_key = self.private_to or self.current_room
        msg={"type":"reaction_display","from":sender,"emoji":emoji,
             "text":f"{emoji}  {sender}","time":""}
        self._add_msg(chat_key, msg)

    def _on_deleted(self,pkt):
        msg={"type":"system","text":f"🗑 Message deleted by {pkt.get('by','?')}"}
        self._add_msg(self.current_room,msg)

    def _on_read(self,pkt):
        by=pkt.get('by','?')
        msg={"type":"system","text":f"✓✓ Seen by {by}"}
        self._add_msg(self.current_room,msg)

    def _on_status(self,pkt):
        user=pkt.get('username',''); status=pkt.get('status','online')
        self.user_info.setdefault(user,{})['status']=status
        # update peer status if this chat is open
        if self.peer_name.cget('text')==user:
            color=GREEN_WA if status=='online' else YELLOW_WA if status=='away' else RED_WA if status=='busy' else TXT_S
            self.peer_status.config(text=f"● {status}",fg=color)

    def _on_joined(self,pkt):
        u=pkt.get('username','')
        msg={"type":"system","text":f"● {u} came online","time":""}
        self._add_msg(self.current_room,msg)
        self.client.get_users()

    def _on_left(self,pkt):
        u=pkt.get('username','')
        msg={"type":"system","text":f"○ {u} went offline","time":""}
        self._add_msg(self.current_room,msg)
        self.client.get_users()

    def _on_added_group(self,pkt):
        group=pkt.get('group',''); by=pkt.get('by','')
        self._add_chat_entry(group,f"Added by {by}",True)
        msg={"type":"system","text":f"👥 You were added to group '{group}' by {by}","time":""}
        self.chat_messages.setdefault(group,[]).append(msg)

    def _on_typing(self,who):
        self.typing_users.add(who)
        names=", ".join(self.typing_users)
        self.typing_lbl.config(text=f"{names} {'is' if len(self.typing_users)==1 else 'are'} typing...")

    def _stop_typing(self,who):
        self.typing_users.discard(who)
        self.typing_lbl.config(text=", ".join(self.typing_users)+" is typing..." if self.typing_users else "")

    # ─────────────────────────────────────────────────────────────────────────
    #  CALL HANDLERS
    # ─────────────────────────────────────────────────────────────────────────
    def _on_incoming_call(self,pkt):
        caller=pkt.get('from','?'); call_id=pkt.get('call_id'); call_type=pkt.get('call_type','voice')
        IncomingCallPopup(self.root,caller,call_id,call_type,self._accept_call,self._reject_call)

    def _on_ringing(self,pkt):
        self.current_call_id=pkt.get('call_id')
        self.call_lbl.config(text=f"📞 Calling {pkt.get('to','')}...")
        self.peer_status.config(text="📞 Ringing...",fg=GREEN_WA)

    def _on_call_accepted(self,pkt):
        other=pkt.get('from','?'); call_id=pkt.get('call_id'); call_type=pkt.get('call_type','voice')
        self.current_call_id=call_id
        self.call_lbl.config(text=f"🔴 On call")
        self.peer_status.config(text=f"🔴 On {call_type} call",fg=GREEN_WA)
        if call_type=='video':
            self.video_win=VideoCallWindow(self.root,self.client,call_id,other,self.video,self.voice)
        elif self.voice.available:
            self.voice.start_capture(lambda c:self.client.send_audio(call_id,c))

    def _on_call_rejected(self,pkt):
        self.call_lbl.config(text=""); self.current_call_id=None
        msg={"type":"system","text":f"❌ Call rejected: {pkt.get('reason','Declined')}","time":""}
        self._add_msg(self.current_room,msg)

    def _on_call_ended(self,pkt):
        self.call_lbl.config(text=""); self.current_call_id=None
        if self.video_win: self.video_win.on_call_ended(); self.video_win=None
        self.voice.stop_capture(); self.voice.stop_playback()
        msg={"type":"system","text":f"📵 Call ended by {pkt.get('from','?')}","time":""}
        self._add_msg(self.current_room,msg)

    def _accept_call(self,call_id,call_type):
        self.current_call_id=call_id; self.client.call_accept(call_id)
        self.call_lbl.config(text="🔴 On call")
        if call_type=='video':
            self.video_win=VideoCallWindow(self.root,self.client,call_id,"Caller",self.video,self.voice)
        elif self.voice.available:
            self.voice.start_capture(lambda c:self.client.send_audio(call_id,c))

    def _reject_call(self,call_id): self.client.call_reject(call_id)

    def _start_call(self,call_type):
        target=self.peer_name.cget('text')
        if not target or target==self.current_room:
            messagebox.showinfo("Call","Open a DM first to call someone"); return
        self.client.call_request(target,call_type)

    def _end_call(self):
        if self.current_call_id: self.client.call_end(self.current_call_id)
        if self.video_win: self.video_win.on_call_ended(); self.video_win=None
        self.voice.stop_capture(); self.voice.stop_playback()
        self.call_lbl.config(text=""); self.current_call_id=None

    # ─────────────────────────────────────────────────────────────────────────
    #  SEND
    # ─────────────────────────────────────────────────────────────────────────
    def _send_msg(self,event=None):
        text=self.msg_var.get().strip()
        if not text: return
        self.msg_var.set("")
        reply=self.reply_lbl.cget("text").replace("↩ Replying to: ","") if self.reply_to else None
        self.client.send_message(text,to=self.private_to,reply_to=reply)
        self._clear_reply(); self.client.stop_typing()

    def _open_attach_menu(self):
        # position popup above the attach button
        x = self.attach_btn.winfo_rootx()
        y = self.attach_btn.winfo_rooty()

        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.configure(bg=LP_SELECT)
        popup.attributes("-topmost", True)

        options = [
            ("Photos & Videos",  "#d946ef", "🖼", self._send_image),
            ("Document",         "#60a5fa", "📄", self._send_document),
            ("Audio",            "#34d399", "🎵", self._send_audio_file),
            ("Camera",           "#fb923c", "📷", self._send_camera),
            ("Location",         "#f87171", "📍", self._send_location),
            ("Contact",          "#a78bfa", "👤", self._send_contact),
            ("Sticker",          "#fbbf24", "⭐", self._send_sticker),
        ]

        for label, color, icon, cmd in reversed(options):
            row = tk.Frame(popup, bg=LP_SELECT, cursor="hand2")
            row.pack(fill="x", padx=0, pady=0)

            def _enter(e, r=row, c=color):
                r.config(bg=LP_HOVER)
                for ch in r.winfo_children():
                    try: ch.config(bg=LP_HOVER)
                    except: pass
            def _leave(e, r=row):
                r.config(bg=LP_SELECT)
                for ch in r.winfo_children():
                    try: ch.config(bg=LP_SELECT)
                    except: pass
            row.bind("<Enter>", _enter)
            row.bind("<Leave>", _leave)

            # colored circle
            circle = tk.Label(row, text="  ", font=FSS, bg=color,
                              width=2, relief="flat")
            circle.pack(side="left", padx=(0,0), ipady=14)

            # icon
            ico_lbl = tk.Label(row, text=icon, font=("Segoe UI Emoji",13),
                               bg=LP_SELECT, fg=TXT_W)
            ico_lbl.pack(side="left", padx=(10,4), pady=10)

            # label
            lbl = tk.Label(row, text=label, font=F, bg=LP_SELECT, fg=TXT_W, anchor="w", width=16)
            lbl.pack(side="left", padx=(0,16), pady=10)

            def _click(e=None, c=cmd, p=popup): p.destroy(); c()
            for w in [row, circle, ico_lbl, lbl]:
                w.bind("<Button-1>", _click)

            tk.Frame(popup,bg="#1a2634",height=1).pack(fill="x")

        # position popup above button
        popup.update_idletasks()
        pw = popup.winfo_reqwidth()
        ph = popup.winfo_reqheight()
        popup.geometry(f"{pw}x{ph}+{x - pw + 40}+{y - ph - 8}")

        # close on click outside
        popup.bind("<FocusOut>", lambda e: popup.destroy())
        popup.focus_set()

    def _show_sender_bubble(self, path):
        """Immediately show file bubble on sender side — called before/after network send"""
        import datetime
        fname = os.path.basename(path)
        size  = os.path.getsize(path)
        ext   = fname.split('.')[-1].lower()
        ftype = 'image' if ext in ['png','jpg','jpeg','gif','bmp','webp'] else                 'video' if ext in ['mp4','avi','mov','mkv'] else                 'audio' if ext in ['mp3','wav','ogg','m4a','aac','flac'] else 'other'
        ts = datetime.datetime.now().strftime('%H:%M:%S')
        pkt = {
            "type"       : "file",
            "from"       : self.username,
            "filename"   : fname,
            "size"       : size,
            "file_type"  : ftype,
            "time"       : ts,
            "private"    : self.private_to is not None,
            "_saved_path": path,
        }
        chat_key = self.private_to or self.current_room
        self._add_msg(chat_key, pkt)
        # update left panel preview
        self._add_chat_entry(chat_key, f"📎 {fname}", False, 0)

    def _network_send_file(self, path):
        """Send file over network in background thread"""
        def _go():
            try: self.client.send_file(path, to=self.private_to)
            except Exception as e: print(f"File send error: {e}")
        threading.Thread(target=_go, daemon=True).start()

    def _send_file(self, path=None, filetypes=None, title="Select file"):
        if path is None:
            path = filedialog.askopenfilename(
                title=title,
                filetypes=filetypes or [("All files","*.*")]
            )
        if not path: return
        if os.path.getsize(path) > 20*1024*1024:
            messagebox.showwarning("Too large","Max 20 MB"); return
        self._show_sender_bubble(path)
        self._network_send_file(path)

    def _send_image(self):
        """Photos & Videos — pick file, show preview, then send"""
        path = filedialog.askopenfilename(
            title="Select Photo or Video",
            filetypes=[("Images & Videos","*.png *.jpg *.jpeg *.gif *.bmp *.webp *.mp4 *.avi *.mov"),("All","*.*")]
        )
        if not path: return
        # show preview window before sending
        self._preview_and_send(path)

    def _preview_and_send(self, path):
        """Show image preview with caption box before sending"""
        fname = os.path.basename(path)
        ext = fname.split('.')[-1].lower()
        is_image = ext in ['png','jpg','jpeg','gif','bmp','webp']

        win = tk.Toplevel(self.root)
        win.title("Send File"); win.geometry("420x500")
        win.configure(bg=LP_TOP); win.resizable(False,False)

        tk.Label(win,text="Send to: " + (self.peer_name.cget('text') or 'Room'),
                 font=FB,bg=LP_TOP,fg=TXT_W).pack(pady=(14,6))

        # preview
        preview_frm = tk.Frame(win,bg="#000",height=300); preview_frm.pack(fill="x",padx=16)
        preview_frm.pack_propagate(False)

        if is_image:
            try:
                from PIL import Image, ImageTk
                img = Image.open(path)
                img.thumbnail((388, 290))
                photo = ImageTk.PhotoImage(img)
                lbl = tk.Label(preview_frm,image=photo,bg="#000")
                lbl.image = photo
                lbl.pack(expand=True)
            except:
                tk.Label(preview_frm,text=f"🖼 {fname}",font=F,bg="#000",fg=TXT_W).pack(expand=True)
        else:
            icon = "🎥" if ext in ['mp4','avi','mov','mkv'] else "📄"
            tk.Label(preview_frm,text=f"{icon}  {fname}",font=FB,bg="#000",fg=TXT_W,
                     justify="center").pack(expand=True)

        # file info
        size = os.path.getsize(path)
        tk.Label(win,text=f"{fname}  •  {self._fmt(size)}",font=FSS,
                 bg=LP_TOP,fg=TXT_S).pack(pady=6)

        # caption
        tk.Label(win,text="Add a caption (optional)",font=FSS,bg=LP_TOP,fg=TXT_S).pack()
        cap_e = tk.Entry(win,font=F,bg=LP_SELECT,fg=TXT_W,insertbackground=GREEN_WA,relief="flat")
        cap_e.pack(fill="x",padx=16,ipady=8,pady=(4,12))

        def _do_send():
            caption = cap_e.get().strip()
            win.destroy()
            if size > 20*1024*1024:
                messagebox.showwarning("Too large","Max 20 MB"); return
            # show on sender side immediately
            self._show_sender_bubble(path)
            def _go():
                try:
                    self.client.send_file(path, to=self.private_to)
                    if caption:
                        self.client.send_message(caption, to=self.private_to)
                except Exception as e: print(f"Send error: {e}")
            threading.Thread(target=_go,daemon=True).start()

        btn_frm = tk.Frame(win,bg=LP_TOP); btn_frm.pack(fill="x",padx=16)
        tk.Button(btn_frm,text="Cancel",font=FB,bg=LP_SELECT,fg=TXT_W,
                  relief="flat",cursor="hand2",pady=8,padx=20,
                  command=win.destroy).pack(side="left")
        tk.Button(btn_frm,text="Send  ➤",font=FB,bg=GREEN_WA,fg="white",
                  activebackground=GREEN_LT,relief="flat",cursor="hand2",pady=8,padx=20,
                  command=_do_send).pack(side="right")

    def _send_document(self):
        """Document — pick file and send immediately with file info bubble"""
        path = filedialog.askopenfilename(
            title="Select Document",
            filetypes=[("Documents","*.pdf *.docx *.doc *.xlsx *.xls *.txt *.pptx *.csv *.zip *.rar"),("All","*.*")]
        )
        if not path: return
        if os.path.getsize(path) > 20*1024*1024:
            messagebox.showwarning("Too large","Max 20 MB"); return
        self._show_sender_bubble(path)
        self._network_send_file(path)

    def _send_audio_file(self):
        """Audio — pick audio file, show waveform placeholder, send"""
        path = filedialog.askopenfilename(
            title="Select Audio",
            filetypes=[("Audio Files","*.mp3 *.wav *.ogg *.m4a *.aac *.flac"),("All","*.*")]
        )
        if not path: return
        fname = os.path.basename(path)
        size  = os.path.getsize(path)

        win = tk.Toplevel(self.root)
        win.title("Send Audio"); win.geometry("360x200")
        win.configure(bg=LP_TOP); win.resizable(False,False)

        tk.Label(win,text="🎵 Send Audio",font=FB,bg=LP_TOP,fg=TXT_W).pack(pady=(18,8))

        # fake waveform display
        wf_frm = tk.Frame(win,bg=BUBBLE_YOU,padx=16,pady=12); wf_frm.pack(padx=20,fill="x")
        tk.Label(wf_frm,text="🎵",font=("Segoe UI Emoji",20),bg=BUBBLE_YOU,fg=GREEN_WA).pack(side="left")
        info = tk.Frame(wf_frm,bg=BUBBLE_YOU); info.pack(side="left",padx=10)
        tk.Label(info,text=fname,font=FB,bg=BUBBLE_YOU,fg=TXT_W,anchor="w").pack(anchor="w")
        tk.Label(info,text=self._fmt(size),font=FSS,bg=BUBBLE_YOU,fg=TXT_S,anchor="w").pack(anchor="w")
        # waveform bars
        bars = tk.Frame(wf_frm,bg=BUBBLE_YOU); bars.pack(side="right")
        import random
        for _ in range(20):
            h=random.randint(6,24)
            tk.Frame(bars,bg=GREEN_WA,width=3,height=h).pack(side="left",padx=1)

        def _do_send():
            win.destroy()
            self._show_sender_bubble(path)
            self._network_send_file(path)

        bf = tk.Frame(win,bg=LP_TOP); bf.pack(pady=14,fill="x",padx=20)
        tk.Button(bf,text="Cancel",font=FB,bg=LP_SELECT,fg=TXT_W,relief="flat",
                  cursor="hand2",pady=8,padx=16,command=win.destroy).pack(side="left")
        tk.Button(bf,text="Send  ➤",font=FB,bg=GREEN_WA,fg="white",
                  activebackground=GREEN_LT,relief="flat",cursor="hand2",
                  pady=8,padx=16,command=_do_send).pack(side="right")

    def _send_camera(self):
        """Camera — live webcam preview, click capture to snap and send"""
        if not self.video.available:
            messagebox.showinfo("Camera","Install opencv-python and Pillow:\npip install opencv-python Pillow")
            return
        cap = self.video.cv2.VideoCapture(0)
        if not cap.isOpened():
            messagebox.showwarning("Camera","No camera found on this device"); return

        win = tk.Toplevel(self.root)
        win.title("Camera"); win.geometry("500x460")
        win.configure(bg="#000"); win.resizable(False,False)

        tk.Label(win,text="📷 Camera",font=FB,bg="#000",fg=TXT_W).pack(pady=(10,4))
        cam_lbl = tk.Label(win,bg="#000"); cam_lbl.pack()
        status_lbl = tk.Label(win,text="Live preview",font=FSS,bg="#000",fg=TXT_S)
        status_lbl.pack(pady=4)

        captured = [None]  # store captured frame
        running  = [True]

        def _update():
            if not running[0]: return
            ret, frame = cap.read()
            if ret:
                frame_rgb = self.video.cv2.cvtColor(frame, self.video.cv2.COLOR_BGR2RGB)
                frame_rgb = self.video.cv2.resize(frame_rgb,(460,340))
                photo = self.video.ImageTk.PhotoImage(
                    image=self.video.Image.fromarray(frame_rgb))
                cam_lbl.config(image=photo); cam_lbl.image=photo
            win.after(30, _update)

        _update()

        def _capture():
            ret, frame = cap.read()
            if not ret: return
            captured[0] = frame
            running[0] = False
            # show captured image
            frame_rgb = self.video.cv2.cvtColor(frame, self.video.cv2.COLOR_BGR2RGB)
            frame_rgb = self.video.cv2.resize(frame_rgb,(460,340))
            photo = self.video.ImageTk.PhotoImage(image=self.video.Image.fromarray(frame_rgb))
            cam_lbl.config(image=photo); cam_lbl.image=photo
            status_lbl.config(text="✅ Photo captured — click Send or Retake",fg=GREEN_WA)
            capture_btn.config(state="disabled")
            send_btn.config(state="normal")
            retake_btn.config(state="normal")

        def _retake():
            captured[0]=None; running[0]=True
            status_lbl.config(text="Live preview",fg=TXT_S)
            capture_btn.config(state="normal")
            send_btn.config(state="disabled")
            retake_btn.config(state="disabled")
            _update()

        def _send_photo():
            if captured[0] is None: return
            import tempfile
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg",delete=False)
            self.video.cv2.imwrite(tmp.name, captured[0])
            running[0]=False; cap.release(); win.destroy()
            self._show_sender_bubble(tmp.name)
            self._network_send_file(tmp.name)

        def _close():
            running[0]=False; cap.release(); win.destroy()

        win.protocol("WM_DELETE_WINDOW",_close)
        bf = tk.Frame(win,bg="#000"); bf.pack(pady=6)
        capture_btn = tk.Button(bf,text="📷 Capture",font=FB,bg=GREEN_WA,fg="white",
                                 activebackground=GREEN_LT,relief="flat",cursor="hand2",
                                 pady=8,padx=18,command=_capture)
        capture_btn.pack(side="left",padx=8)
        retake_btn = tk.Button(bf,text="🔄 Retake",font=FB,bg=LP_SELECT,fg=TXT_W,
                                relief="flat",cursor="hand2",pady=8,padx=14,
                                state="disabled",command=_retake)
        retake_btn.pack(side="left",padx=8)
        send_btn = tk.Button(bf,text="Send  ➤",font=FB,bg=BLUE_WA,fg="white",
                              activebackground=BLUE_WA,relief="flat",cursor="hand2",
                              pady=8,padx=14,state="disabled",command=_send_photo)
        send_btn.pack(side="left",padx=8)
        tk.Button(bf,text="✖ Close",font=FB,bg=RED_WA,fg="white",relief="flat",
                  cursor="hand2",pady=8,padx=10,command=_close).pack(side="left",padx=8)

    def _send_location(self):
        """Location — enter address, auto-fills coordinates, sends Google Maps link"""
        win = tk.Toplevel(self.root)
        win.title("Share Location"); win.geometry("400x340")
        win.configure(bg=LP_TOP); win.resizable(False,False)

        tk.Label(win,text="📍 Share Location",font=FB,bg=LP_TOP,fg=TXT_W).pack(pady=(18,4))
        tk.Label(win,text="Type your location name",font=FSS,bg=LP_TOP,fg=TXT_S).pack()

        loc_e = tk.Entry(win,font=F,bg=LP_SELECT,fg=TXT_W,insertbackground=GREEN_WA,
                         relief="flat",width=36)
        loc_e.pack(ipady=9,padx=20,pady=(4,12)); loc_e.insert(0,"Pune, Maharashtra, India")
        loc_e.focus()

        # map preview placeholder
        map_frm = tk.Frame(win,bg="#182229",height=120); map_frm.pack(fill="x",padx=20)
        map_frm.pack_propagate(False)
        tk.Label(map_frm,text="🗺",font=("Segoe UI Emoji",36),bg="#182229",fg=TXT_S).pack(expand=True)

        # coords row
        cf = tk.Frame(win,bg=LP_TOP); cf.pack(pady=8)
        tk.Label(cf,text="Lat:",font=FSS,bg=LP_TOP,fg=TXT_S).pack(side="left")
        lat_e=tk.Entry(cf,font=FS,bg=LP_SELECT,fg=TXT_W,relief="flat",width=12)
        lat_e.pack(side="left",padx=4,ipady=5); lat_e.insert(0,"18.5204")
        tk.Label(cf,text="Lon:",font=FSS,bg=LP_TOP,fg=TXT_S).pack(side="left",padx=(8,0))
        lon_e=tk.Entry(cf,font=FS,bg=LP_SELECT,fg=TXT_W,relief="flat",width=12)
        lon_e.pack(side="left",padx=4,ipady=5); lon_e.insert(0,"73.8567")

        def _share():
            loc=loc_e.get().strip(); lat=lat_e.get().strip(); lon=lon_e.get().strip()
            if not loc: messagebox.showwarning("Error","Enter a location",parent=win); return
            maps_url = f"https://maps.google.com/?q={lat},{lon}"
            msg = "📍 Location: " + loc + " | Lat: " + lat + ", Lon: " + lon + " | Maps: " + maps_url
            self.client.send_message(msg, to=self.private_to)
            win.destroy()

        bf = tk.Frame(win,bg=LP_TOP); bf.pack(fill="x",padx=20,pady=(4,0))
        tk.Button(bf,text="Cancel",font=FB,bg=LP_SELECT,fg=TXT_W,relief="flat",
                  cursor="hand2",pady=8,padx=16,command=win.destroy).pack(side="left")
        tk.Button(bf,text="Send Location  📍",font=FB,bg=GREEN_WA,fg="white",
                  activebackground=GREEN_LT,relief="flat",cursor="hand2",
                  pady=8,padx=12,command=_share).pack(side="right")

    def _send_contact(self):
        """Contact — fill in details and send a formatted contact card"""
        win = tk.Toplevel(self.root)
        win.title("Share Contact"); win.geometry("380x380")
        win.configure(bg=LP_TOP); win.resizable(False,False)

        tk.Label(win,text="👤 New Contact",font=FB,bg=LP_TOP,fg=TXT_W).pack(pady=(18,6))

        # avatar preview
        av_frm=tk.Frame(win,bg=LP_TOP); av_frm.pack(pady=(0,12))
        self._contact_av=tk.Label(av_frm,text="👤",font=("Segoe UI Emoji",36),
                                   bg=LP_SELECT,fg=TXT_W,padx=16,pady=8)
        self._contact_av.pack()

        fields={}
        for lbl,placeholder,icon in [
            ("Full Name","e.g. Dharati Sharma","👤"),
            ("Phone Number","e.g. +91 98765 43210","📞"),
            ("Email","e.g. dharati@email.com","✉"),
            ("Company","e.g. TechCorp (optional)","🏢"),
        ]:
            row=tk.Frame(win,bg=LP_TOP); row.pack(fill="x",padx=20,pady=2)
            tk.Label(row,text=icon,font=("Segoe UI Emoji",13),bg=LP_TOP,fg=TXT_S).pack(side="left",padx=(0,8))
            e=tk.Entry(row,font=F,bg=LP_SELECT,fg=TXT_W,insertbackground=GREEN_WA,
                       relief="flat")
            e.pack(side="left",fill="x",expand=True,ipady=7)
            e.insert(0,placeholder); e.config(fg=TXT_S)
            def _focus_in(ev,entry=e,ph=placeholder):
                if entry.get()==ph: entry.delete(0,"end"); entry.config(fg=TXT_W)
            def _focus_out(ev,entry=e,ph=placeholder):
                if not entry.get(): entry.insert(0,ph); entry.config(fg=TXT_S)
            e.bind("<FocusIn>",_focus_in); e.bind("<FocusOut>",_focus_out)
            fields[lbl]=e

        def _get(lbl):
            v=fields[lbl].get()
            placeholders={"Full Name":"e.g. Dharati Sharma","Phone Number":"e.g. +91 98765 43210",
                          "Email":"e.g. dharati@email.com","Company":"e.g. TechCorp (optional)"}
            return "" if v==placeholders.get(lbl,"") else v

        def _share():
            name=_get("Full Name"); phone=_get("Phone Number")
            email=_get("Email"); company=_get("Company")
            if not name: messagebox.showwarning("Error","Enter contact name",parent=win); return
            msg = "👤 Contact: " + name + " | Phone: " + (phone or "N/A") + " | Email: " + (email or "N/A") + " | Company: " + (company or "N/A")
            self.client.send_message(msg,to=self.private_to); win.destroy()

        bf=tk.Frame(win,bg=LP_TOP); bf.pack(fill="x",padx=20,pady=(10,0))
        tk.Button(bf,text="Cancel",font=FB,bg=LP_SELECT,fg=TXT_W,relief="flat",
                  cursor="hand2",pady=8,padx=16,command=win.destroy).pack(side="left")
        tk.Button(bf,text="Send Contact  👤",font=FB,bg=GREEN_WA,fg="white",
                  activebackground=GREEN_LT,relief="flat",cursor="hand2",
                  pady=8,padx=12,command=_share).pack(side="right")

    def _send_sticker(self):
        """Sticker picker — categories with large emoji stickers"""
        win = tk.Toplevel(self.root)
        win.title("Stickers"); win.geometry("420x380")
        win.configure(bg=LP_TOP)

        tk.Label(win,text="⭐ Stickers",font=FB,bg=LP_TOP,fg=TXT_W).pack(pady=(14,6))

        # category tabs
        categories = {
            "😊 Faces":  ["😀","😂","🤣","😍","🥳","😎","😭","😡","🥺","😇","😴","🤔","😱","🤯","🥸"],
            "❤️ Love":   ["❤️","🧡","💛","💚","💙","💜","🖤","💖","💗","💓","💞","💝","💘","💟","❣️"],
            "🎉 Fun":    ["🎉","🔥","⭐","💯","👏","🙏","💪","🤝","✌️","🤙","👋","🎊","🎈","🎁","🏆"],
            "🐾 Animals":["🐶","🐱","🐸","🐼","🦁","🐯","🐨","🐮","🦊","🐺","🐷","🐙","🦋","🐝","🦄"],
            "🍕 Food":   ["🍕","🍔","🍟","🌮","🍜","🎂","🍩","🍦","🍣","🍎","🍓","🥑","🍺","☕","🧃"],
            "⚽ Sports": ["⚽","🏀","🎮","🎵","🎬","📚","🚀","✈️","🌈","⭐","🌙","☀️","🎸","🏋️","🎯"],
        }

        cat_var = tk.StringVar(value="😊 Faces")

        # tab bar
        tab_frm=tk.Frame(win,bg=LP_SELECT); tab_frm.pack(fill="x",padx=0)
        tab_btns={}
        def _switch(cat):
            cat_var.set(cat)
            for c,b in tab_btns.items():
                b.config(bg=GREEN_WA if c==cat else LP_SELECT,
                         fg="white" if c==cat else TXT_S)
            _render(cat)

        for cat in categories:
            b=tk.Button(tab_frm,text=cat.split()[0],font=("Segoe UI Emoji",13),
                        bg=LP_SELECT,fg=TXT_S,relief="flat",cursor="hand2",
                        padx=8,pady=6,
                        command=lambda c=cat:_switch(c))
            b.pack(side="left",padx=1)
            tab_btns[cat]=b
        tab_btns["😊 Faces"].config(bg=GREEN_WA,fg="white")

        # sticker grid
        grid_frm=tk.Frame(win,bg=LP_TOP); grid_frm.pack(fill="both",expand=True,padx=8,pady=8)

        def _render(cat):
            for w in grid_frm.winfo_children(): w.destroy()
            stickers=categories[cat]; col=0; row_frm=None
            for i,s in enumerate(stickers):
                if i%5==0:
                    row_frm=tk.Frame(grid_frm,bg=LP_TOP); row_frm.pack(anchor="w")
                tk.Button(row_frm,text=s,font=("Segoe UI Emoji",28),
                          bg=LP_TOP,activebackground=LP_SELECT,
                          relief="flat",cursor="hand2",bd=0,padx=6,pady=6,
                          command=lambda x=s:[self.client.send_message(x,to=self.private_to),win.destroy()]
                          ).pack(side="left")

        _render("😊 Faces")

    def _send_reaction(self, emoji, color):
        """Send reaction and show it on sender side immediately"""
        # animate the button briefly
        btn = self._react_btns.get(emoji)
        if btn:
            btn.config(bg=color)
            self.root.after(400, lambda: btn.config(bg=RP_INPUT))
        # show in own chat immediately
        chat_key = self.private_to or self.current_room
        msg = {"type":"reaction_display","from":self.username,
               "emoji":emoji,"text":f"{emoji}  You reacted","time":""}
        self._add_msg(chat_key, msg)
        # send to others
        self.client.send_reaction(emoji)

    def _on_key(self,event=None):
        self.client.send_typing()
        if self.typing_timer: self.root.after_cancel(self.typing_timer)
        self.typing_timer=self.root.after(3000,lambda:self.client.stop_typing())

    def _open_emoji(self):
        EmojiPicker(self.root,lambda e:self.msg_var.set(self.msg_var.get()+e))

    def _set_reply(self,text):
        self.reply_to=text
        self.reply_lbl.config(text=f"↩ Replying to: {text[:50]}")
        self.reply_bar.pack(fill="x",before=self.typing_lbl)

    def _clear_reply(self):
        self.reply_to=None
        try: self.reply_bar.pack_forget()
        except: pass

    def _copy_text(self,text):
        self.root.clipboard_clear(); self.root.clipboard_append(text)

    def _forward(self,pkt):
        text=pkt.get('text','')
        self.client.send_message(text,to=self.private_to,reply_to=None)

    # ─────────────────────────────────────────────────────────────────────────
    #  TOOLBAR ACTIONS
    # ─────────────────────────────────────────────────────────────────────────
    def _new_group(self):
        others=[u for u in self.online_users if u!=self.username]
        if not others: messagebox.showinfo("Group","No other users online"); return
        win=tk.Toplevel(self.root); win.title("New Group")
        win.geometry("340,400".replace(",","x")); win.configure(bg=LP_TOP)
        tk.Label(win,text="👥 New Group",font=FT,bg=LP_TOP,fg=TXT_W).pack(pady=(20,8))
        tk.Label(win,text="Group name",font=FSS,bg=LP_TOP,fg=TXT_S).pack()
        name_e=tk.Entry(win,font=F,bg=LP_SELECT,fg=TXT_W,insertbackground=GREEN_WA,relief="flat")
        name_e.pack(fill="x",padx=20,ipady=8,pady=(4,12))
        tk.Label(win,text="Add participants",font=FSS,bg=LP_TOP,fg=TXT_S).pack()
        lb=tk.Listbox(win,font=F,bg=LP_SELECT,fg=TXT_W,selectmode="multiple",
                      relief="flat",bd=0,highlightthickness=0,height=8,
                      selectbackground=GREEN_WA)
        lb.pack(fill="x",padx=20,pady=4)
        for u in others: lb.insert("end",f"  {u}")

        def _create():
            name=name_e.get().strip()
            sel=[lb.get(i).strip() for i in lb.curselection()]
            if not name: messagebox.showwarning("Error","Enter group name",parent=win); return
            if not sel: messagebox.showwarning("Error","Select at least one member",parent=win); return
            self.client.create_group(name,sel)
            self._add_chat_entry(name,"Group Chat",True)
            self.chat_messages[name]=[]
            messagebox.showinfo("Created",f"Group '{name}' created!",parent=win)
            win.destroy()

        tk.Button(win,text="Create Group",font=FB,bg=GREEN_WA,fg="white",
                  activebackground=GREEN_LT,relief="flat",cursor="hand2",
                  pady=10,command=_create).pack(fill="x",padx=20,pady=(12,0))

    def _open_search(self):
        win=tk.Toplevel(self.root); win.title("Search")
        win.geometry("500,420".replace(",","x")); win.configure(bg=LP_TOP)
        tk.Label(win,text="🔍 Search Messages",font=FT,bg=LP_TOP,fg=TXT_W).pack(pady=(16,8))
        sv=tk.StringVar()
        se=tk.Entry(win,textvariable=sv,font=F,bg=LP_SELECT,fg=TXT_W,
                    insertbackground=GREEN_WA,relief="flat")
        se.pack(fill="x",padx=16,ipady=8,pady=(0,8))
        res=tk.Text(win,font=FS,bg=RP_BG,fg=TXT_W,relief="flat",state="disabled",
                    wrap="word",padx=10,pady=8)
        res.pack(fill="both",expand=True,padx=16,pady=(0,16))

        def _search(*a):
            q=sv.get().strip().lower()
            res.config(state="normal"); res.delete("1.0","end")
            if not q: res.config(state="disabled"); return
            found=0
            for msgs in self.chat_messages.values():
                for m in msgs:
                    if q in m.get('text','').lower():
                        res.insert("end",f"[{m.get('time','')}] {m.get('from','?')}: {m.get('text','')}\n\n")
                        found+=1
            if not found: res.insert("end","No results found.")
            res.config(state="disabled")

        sv.trace('w',_search)
        se.focus()

    def _show_menu(self):
        menu=tk.Menu(self.root,tearoff=0,bg=LP_SELECT,fg=TXT_W,
                     activebackground=LP_HOVER,font=FS)
        menu.add_command(label="👤  My Profile",command=self._open_profile)
        menu.add_command(label="● Online",command=lambda:self.client.set_status('online'))
        menu.add_command(label="◑ Away",  command=lambda:self.client.set_status('away'))
        menu.add_command(label="○ Busy",  command=lambda:self.client.set_status('busy'))
        menu.add_separator()
        menu.add_command(label="📵  End Call",command=self._end_call)
        try:
            x=self.left.winfo_rootx()+self.left.winfo_width()-10
            y=56
            menu.tk_popup(x,y)
        finally: menu.grab_release()

    def _open_profile(self):
        win=tk.Toplevel(self.root); win.title("Profile")
        win.geometry("340,280".replace(",","x")); win.configure(bg=LP_TOP)
        tk.Label(win,text=self.username[0].upper(),font=("Segoe UI",32,"bold"),
                 bg=GREEN_WA,fg="white",width=3).pack(pady=(20,8))
        tk.Label(win,text=self.username,font=FT,bg=LP_TOP,fg=TXT_W).pack()
        tk.Label(win,text="About",font=FSS,bg=LP_TOP,fg=TXT_S).pack(pady=(12,2))
        ae=tk.Entry(win,font=F,bg=LP_SELECT,fg=TXT_W,insertbackground=GREEN_WA,relief="flat",width=32)
        ae.pack(ipady=8,padx=20); ae.insert(0,"Hey there! I am using ChatNet")
        tk.Button(win,text="Save",font=FB,bg=GREEN_WA,fg="white",
                  activebackground=GREEN_LT,relief="flat",cursor="hand2",pady=8,padx=24,
                  command=lambda:[self.client.update_profile(ae.get()),win.destroy()]
                  ).pack(pady=(16,0))

    # ─────────────────────────────────────────────────────────────────────────
    #  UTILS
    # ─────────────────────────────────────────────────────────────────────────
    def _fmt(self,n):
        if n<1024: return f"{n} B"
        if n<1<<20: return f"{n/1024:.1f} KB"
        return f"{n/1<<20:.1f} MB"

    def _open_path(self, path):
        """Open any file with the default system application"""
        if not path:
            messagebox.showwarning("File","No file path available"); return
        if not os.path.exists(path):
            messagebox.showwarning("File Not Found",
                f"File not found:\n{path}\n\nIt may have been moved or deleted.")
            return
        try:
            if os.name == 'nt':
                os.startfile(path)
            elif os.uname().sysname == 'Darwin':
                os.system(f"open '{path}'")
            else:
                os.system(f"xdg-open '{path}'")
        except Exception as e:
            messagebox.showerror("Cannot Open", f"Could not open file:\n{e}")

    def _bind_all_children(self, widget, event, callback):
        """Bind event to widget and ALL its children recursively"""
        widget.bind(event, callback)
        for child in widget.winfo_children():
            self._bind_all_children(child, event, callback)

    def _file_doc_bubble(self,bubble,color,icon,fname,sz,saved,open_fn=None):
        """Document style file bubble like WhatsApp - click anywhere to open"""
        ext = fname.split('.')[-1].upper() if '.' in fname else 'FILE'
        badge_colors = {
            'PDF':'#e53935','DOC':'#1565c0','DOCX':'#1565c0',
            'XLS':'#2e7d32','XLSX':'#2e7d32','PPT':'#e65100',
            'PPTX':'#e65100','ZIP':'#6a1b9a','RAR':'#6a1b9a',
            'TXT':'#546e7a','CSV':'#00838f','PNG':'#0277bd',
            'JPG':'#0277bd','JPEG':'#0277bd','MP3':'#558b2f',
            'MP4':'#6a1b9a','AVI':'#6a1b9a',
        }
        badge_color = badge_colors.get(ext, BLUE_WA)

        def _click(e=None):
            self._open_path(saved)

        # whole card is one big clickable area
        card = tk.Frame(bubble, bg="#0b1f2e", cursor="hand2")
        card.pack(fill="x", pady=(0,2))

        # top row: badge + info + arrow
        row = tk.Frame(card, bg="#0b1f2e", padx=10, pady=12)
        row.pack(fill="x")

        # colored badge
        badge = tk.Frame(row, bg=badge_color, width=50, height=50)
        badge.pack(side="left"); badge.pack_propagate(False)
        tk.Label(badge, text=ext[:4], font=("Segoe UI",8,"bold"),
                 bg=badge_color, fg="white").pack(expand=True)

        # file name + size
        info = tk.Frame(row, bg="#0b1f2e")
        info.pack(side="left", padx=12, fill="x", expand=True)
        tk.Label(info, text=fname, font=FB, bg="#0b1f2e", fg=TXT_W,
                 anchor="w", wraplength=240).pack(anchor="w")
        tk.Label(info, text=f"{ext}  •  {self._fmt(sz)}", font=FSS,
                 bg="#0b1f2e", fg=TXT_S, anchor="w").pack(anchor="w")

        # arrow
        tk.Label(row, text="↗", font=("Segoe UI",14,"bold"),
                 bg="#0b1f2e", fg=GREEN_WA).pack(side="right", padx=6)

        # bottom tap hint bar
        hint = tk.Frame(card, bg="#0a1a26", pady=5)
        hint.pack(fill="x")
        tk.Label(hint, text="🖱  Click anywhere to open",
                 font=FSS, bg="#0a1a26", fg=GREEN_WA,
                 cursor="hand2").pack()

        # bind click on EVERYTHING inside card
        self._bind_all_children(card, "<Button-1>", lambda e: _click())
        self._bind_all_children(bubble, "<Button-1>", lambda e: _click())

    def _flash_title(self,chat_key):
        u=self.unread.get(chat_key,0)
        self.root.title(f"[{u} new] ChatNet" if u else "ChatNet")

# ══════════════════════════════════════════════════════════════════════════════
if __name__=='__main__':
    root=tk.Tk(); LoginWindow(root); root.mainloop()
