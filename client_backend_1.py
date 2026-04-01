"""
Chat Client Backend - handles all networking for the GUI
"""

import socket
import threading
import json
import os
import base64
import struct

class ChatClient:
    def __init__(self, host, port, on_packet_cb):
        self.host = host
        self.port = int(port)
        self.on_packet = on_packet_cb
        self.sock = None
        self.connected = False
        self.username = None

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        self.connected = True

    def send_packet(self, payload):
        data = json.dumps(payload).encode('utf-8')
        self.sock.sendall(struct.pack('>I', len(data)) + data)

    def recv_packet(self):
        raw_len = self._recv_exact(4)
        if not raw_len:
            return None
        (length,) = struct.unpack('>I', raw_len)
        raw = self._recv_exact(length)
        if not raw:
            return None
        return json.loads(raw.decode('utf-8'))

    def _recv_exact(self, n):
        buf = b''
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf

    def authenticate(self, username, password, action='login'):
        self.send_packet({"type": "auth", "username": username,
                          "password": password, "action": action})
        resp = self.recv_packet()
        if resp and resp.get('type') == 'auth_ok':
            self.username = username
            return True, None
        return False, resp.get('reason', 'Unknown error') if resp else 'No response'

    def join_room(self, room):
        self.send_packet({"type": "join", "room": room})
        resp = self.recv_packet()
        if resp and resp.get('type') == 'join_ok':
            return True
        return False

    def start_listener(self):
        t = threading.Thread(target=self._listen_loop, daemon=True)
        t.start()

    def _listen_loop(self):
        while self.connected:
            try:
                pkt = self.recv_packet()
                if pkt is None:
                    self.on_packet({"type": "disconnected"})
                    break
                self.on_packet(pkt)
            except Exception as e:
                self.on_packet({"type": "error", "msg": str(e)})
                break

    def send_message(self, text, to=None):
        payload = {"type": "message", "text": text}
        if to:
            payload["to"] = to
        self.send_packet(payload)

    def send_file(self, filepath, to=None):
        filename = os.path.basename(filepath)
        size = os.path.getsize(filepath)
        with open(filepath, 'rb') as f:
            data = base64.b64encode(f.read()).decode('utf-8')
        payload = {"type": "file", "filename": filename, "size": size, "data": data}
        if to:
            payload["to"] = to
        self.send_packet(payload)
        return filename, size

    def save_received_file(self, pkt, save_dir="downloads"):
        os.makedirs(save_dir, exist_ok=True)
        fname = pkt.get('filename', 'file')
        safe = os.path.join(save_dir, fname)
        # avoid overwrite
        base, ext = os.path.splitext(safe)
        i = 1
        while os.path.exists(safe):
            safe = f"{base}_{i}{ext}"
            i += 1
        with open(safe, 'wb') as f:
            f.write(base64.b64decode(pkt.get('data', '')))
        return safe

    def send_typing(self):
        self.send_packet({"type": "typing"})

    def get_users(self):
        self.send_packet({"type": "get_users"})

    def disconnect(self):
        self.connected = False
        try:
            self.sock.close()
        except:
            pass
