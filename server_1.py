"""
ChatNet Server v4 - Full WhatsApp-like Features
"""
import socket, threading, json, os, base64, hashlib, datetime, struct

HOST = '0.0.0.0'
PORT = 9090
UPLOAD_DIR = "server_files"
os.makedirs(UPLOAD_DIR, exist_ok=True)

clients      = {}
rooms        = {}
users_db     = {}
active_calls = {}
message_history = {}  # room -> list of messages
user_status  = {}     # username -> 'online'/'away'/'busy'
lock = threading.Lock()

def hash_pw(pw):   return hashlib.sha256(pw.encode()).hexdigest()
def ts():          return datetime.datetime.now().strftime('%H:%M:%S')
def date_ts():     return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def sys_msg(text): return {"type":"system","text":text,"time":ts()}

def send_pkt(sock, payload):
    data = json.dumps(payload).encode('utf-8')
    sock.sendall(struct.pack('>I', len(data)) + data)

def recv_pkt(sock):
    r = _exact(sock, 4)
    if not r: return None
    (n,) = struct.unpack('>I', r)
    r = _exact(sock, n)
    return json.loads(r.decode('utf-8')) if r else None

def _exact(sock, n):
    buf = b''
    while len(buf) < n:
        try: c = sock.recv(n - len(buf))
        except: return None
        if not c: return None
        buf += c
    return buf

def broadcast(payload, room, exclude=None):
    with lock: members = list(rooms.get(room, set()))
    for u in members:
        if u == exclude: continue
        with lock: info = clients.get(u)
        if info:
            try: send_pkt(info['socket'], payload)
            except: pass

def send_to(username, payload):
    with lock: info = clients.get(username)
    if info:
        try: send_pkt(info['socket'], payload); return True
        except: pass
    return False

def store_message(room, msg):
    with lock:
        message_history.setdefault(room, []).append(msg)
        if len(message_history[room]) > 200:
            message_history[room] = message_history[room][-200:]

def handle_client(conn, addr):
    username = room = None
    try:
        # AUTH
        auth = recv_pkt(conn)
        if not auth or auth.get('type') != 'auth': conn.close(); return
        username = auth.get('username','').strip()
        password = auth.get('password','')
        action   = auth.get('action','login')
        profile_pic = auth.get('profile_pic', '')
        about    = auth.get('about', 'Hey there! I am using ChatNet')

        if not username or not password:
            send_pkt(conn,{"type":"auth_fail","reason":"Empty credentials"}); conn.close(); return

        hashed = hash_pw(password)
        with lock:
            if action == 'register':
                if username in users_db:
                    send_pkt(conn,{"type":"auth_fail","reason":"Username taken"}); conn.close(); return
                users_db[username] = {"password":hashed,"profile_pic":profile_pic,"about":about,"last_seen":date_ts()}
            else:
                if username not in users_db:
                    send_pkt(conn,{"type":"auth_fail","reason":"User not found"}); conn.close(); return
                if users_db[username]["password"] != hashed:
                    send_pkt(conn,{"type":"auth_fail","reason":"Wrong password"}); conn.close(); return
            if username in clients:
                send_pkt(conn,{"type":"auth_fail","reason":"Already logged in"}); conn.close(); return
            clients[username] = {'socket':conn,'address':addr,'room':None,'in_call':False}
            user_status[username] = 'online'

        send_pkt(conn,{"type":"auth_ok","username":username})

        # JOIN
        jp = recv_pkt(conn)
        if not jp or jp.get('type') != 'join': remove_client(username); conn.close(); return
        room = jp.get('room','General').strip() or 'General'
        with lock:
            rooms.setdefault(room, set()).add(username)
            clients[username]['room'] = room

        send_pkt(conn,{"type":"join_ok","room":room})
        broadcast({"type":"system","text":f"📥 {username} joined","time":ts()}, room, exclude=username)
        broadcast({"type":"user_joined","username":username,"status":"online"}, room, exclude=username)

        with lock: members = sorted(rooms.get(room,set()))
        user_info_list = []
        for m in members:
            info = users_db.get(m, {})
            user_info_list.append({
                "username": m,
                "status": user_status.get(m,'online'),
                "about": info.get('about',''),
                "profile_pic": info.get('profile_pic',''),
                "last_seen": info.get('last_seen','')
            })
        send_pkt(conn,{"type":"user_list","users":members,"user_info":user_info_list,"room":room})

        # Send message history
        with lock: history = list(message_history.get(room, []))
        if history:
            send_pkt(conn,{"type":"message_history","messages":history,"room":room})

        # MAIN LOOP
        while True:
            pkt = recv_pkt(conn)
            if not pkt: break
            t = pkt.get('type')

            if t == 'message':
                target = pkt.get('to')
                msg_id = f"{username}_{ts().replace(':','')}_{id(pkt)}"
                payload = {"type":"message","from":username,"text":pkt.get('text',''),
                           "time":ts(),"private":target is not None,
                           "msg_id":msg_id,"reply_to":pkt.get('reply_to'),
                           "forwarded":pkt.get('forwarded',False)}
                if target:
                    with lock: ti = clients.get(target)
                    if ti:
                        send_pkt(ti['socket'], payload)
                        send_pkt(conn, payload)
                        # delivery receipt
                        send_pkt(conn,{"type":"msg_delivered","msg_id":msg_id,"to":target})
                    else:
                        send_pkt(conn, sys_msg(f"User '{target}' not found"))
                else:
                    store_message(room, payload)
                    broadcast(payload, room)

            elif t == 'msg_read':
                msg_id = pkt.get('msg_id'); sender = pkt.get('original_sender')
                send_to(sender, {"type":"msg_read","msg_id":msg_id,"by":username})

            elif t == 'delete_message':
                msg_id = pkt.get('msg_id')
                payload = {"type":"message_deleted","msg_id":msg_id,"by":username,"time":ts()}
                broadcast(payload, room)

            elif t == 'file':
                fname = pkt.get('filename','file'); b64 = pkt.get('data','')
                target = pkt.get('to'); sz = pkt.get('size',0)
                safe = f"{username}_{ts().replace(':','')}_{fname}"
                with open(os.path.join(UPLOAD_DIR,safe),'wb') as f:
                    f.write(base64.b64decode(b64))
                payload = {"type":"file","from":username,"filename":fname,
                           "size":sz,"data":b64,"time":ts(),"private":target is not None,
                           "file_type":pkt.get('file_type','other')}
                if target:
                    with lock: ti = clients.get(target)
                    if ti: send_pkt(ti['socket'], payload); send_pkt(conn, sys_msg(f"File sent to {target}"))
                    else:  send_pkt(conn, sys_msg(f"User '{target}' not found"))
                else:
                    store_message(room, payload)
                    broadcast(payload, room, exclude=username)
                    send_pkt(conn, sys_msg(f"File shared"))

            elif t == 'call_request':
                callee = pkt.get('to'); call_type = pkt.get('call_type','voice')
                if not callee: continue
                with lock: ci = clients.get(callee); already = clients[username].get('in_call',False)
                if already: send_pkt(conn,{"type":"call_rejected","from":callee,"reason":"Already in a call"}); continue
                if not ci:  send_pkt(conn,{"type":"call_rejected","from":callee,"reason":f"{callee} is offline"}); continue
                call_id = f"{username}_{callee}_{ts().replace(':','')}"
                with lock: active_calls[call_id] = {"caller":username,"callee":callee,"status":"ringing","call_type":call_type}
                send_pkt(ci['socket'],{"type":"incoming_call","from":username,"call_id":call_id,"call_type":call_type})
                send_pkt(conn,{"type":"call_ringing","to":callee,"call_id":call_id,"call_type":call_type})

            elif t == 'call_accept':
                call_id = pkt.get('call_id')
                with lock: call = active_calls.get(call_id)
                if call:
                    call['status'] = 'active'; caller = call['caller']; call_type = call.get('call_type','voice')
                    with lock:
                        if username in clients: clients[username]['in_call'] = True
                        if caller in clients:   clients[caller]['in_call']   = True
                    send_to(caller,{"type":"call_accepted","from":username,"call_id":call_id,"call_type":call_type})
                    send_pkt(conn,{"type":"call_accepted","from":caller,"call_id":call_id,"call_type":call_type})

            elif t == 'call_reject':
                call_id = pkt.get('call_id')
                with lock: call = active_calls.pop(call_id, None)
                if call: send_to(call['caller'],{"type":"call_rejected","from":username,"reason":pkt.get('reason','Declined')})

            elif t == 'call_end':
                call_id = pkt.get('call_id')
                with lock:
                    call = active_calls.pop(call_id, None)
                    if username in clients: clients[username]['in_call'] = False
                if call:
                    other = call['callee'] if call['caller']==username else call['caller']
                    with lock:
                        if other in clients: clients[other]['in_call'] = False
                    send_to(other,{"type":"call_ended","from":username,"call_id":call_id})

            elif t == 'audio_chunk':
                call_id = pkt.get('call_id')
                with lock: call = active_calls.get(call_id)
                if call:
                    other = call['callee'] if call['caller']==username else call['caller']
                    send_to(other, pkt)

            elif t == 'video_chunk':
                call_id = pkt.get('call_id')
                with lock: call = active_calls.get(call_id)
                if call:
                    other = call['callee'] if call['caller']==username else call['caller']
                    send_to(other, pkt)

            elif t == 'status_update':
                new_status = pkt.get('status','online')
                with lock: user_status[username] = new_status
                broadcast({"type":"user_status","username":username,"status":new_status}, room, exclude=username)

            elif t == 'typing':
                broadcast({"type":"typing","from":username}, room, exclude=username)

            elif t == 'stop_typing':
                broadcast({"type":"stop_typing","from":username}, room, exclude=username)

            elif t == 'reaction':
                payload = {"type":"reaction","from":username,"emoji":pkt.get('emoji','👍'),
                           "msg_id":pkt.get('msg_id',''),"time":ts()}
                broadcast(payload, room, exclude=username)

            elif t == 'get_users':
                with lock: members = sorted(rooms.get(room,set()))
                send_pkt(conn,{"type":"user_list","users":members,"room":room})

            elif t == 'get_profile':
                target = pkt.get('username')
                with lock: info = users_db.get(target, {})
                send_pkt(conn,{"type":"profile_info","username":target,
                               "about":info.get('about',''),"last_seen":info.get('last_seen',''),
                               "status":user_status.get(target,'offline')})

            elif t == 'update_profile':
                with lock:
                    if username in users_db:
                        if pkt.get('about'): users_db[username]['about'] = pkt.get('about')
                        if pkt.get('profile_pic'): users_db[username]['profile_pic'] = pkt.get('profile_pic')
                send_pkt(conn, sys_msg("Profile updated"))

            elif t == 'create_group':
                group_name = pkt.get('name','')
                members_list = pkt.get('members', [])
                if group_name:
                    with lock: rooms.setdefault(group_name, set()).update(members_list + [username])
                    for m in members_list:
                        send_to(m, {"type":"added_to_group","group":group_name,"by":username})
                    send_pkt(conn, sys_msg(f"Group '{group_name}' created"))

    except Exception as e:
        print(f"[!] {username or addr}: {e}")
    finally:
        if username:
            with lock:
                if username in users_db: users_db[username]['last_seen'] = date_ts()
        remove_client(username, room); conn.close()

def remove_client(username, room=None):
    if not username: return
    with lock:
        info = clients.pop(username, None)
        r = room or (info['room'] if info else None)
        if r and r in rooms: rooms[r].discard(username)
        user_status.pop(username, None)
    if r:
        broadcast(sys_msg(f"📤 {username} left"), r)
        broadcast({"type":"user_left","username":username}, r)
        with lock: members = sorted(rooms.get(r,set()))
        broadcast({"type":"user_list","users":members,"room":r}, r)
    print(f"[-] {username} disconnected")

def start():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT)); s.listen(100)
    print(f"ChatNet v4 Server running on {HOST}:{PORT}")
    while True:
        conn, addr = s.accept()
        threading.Thread(target=handle_client, args=(conn,addr), daemon=True).start()

if __name__ == '__main__': start()

