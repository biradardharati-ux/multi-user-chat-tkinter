# Multi-User Chat Server with File Transfer
### Computer Networks Project — Python TCP Socket + Web GUI

---

## Architecture

```
Browser (Web GUI)
      |
      | WebSocket (ws://localhost:8765)
      |
  bridge.py  ◄──── Translates WebSocket ↔ Raw TCP
      |
      | TCP Socket (localhost:9999)
      |
  server.py  ◄──── Core chat server
      |
  ┌───┴────────────────────────────┐
  │  Clients: A, B, C, D ...      │
  │  Rooms:   #general, #dev ...  │
  │  Files:   server_uploads/     │
  └────────────────────────────────┘

  OR use client.py (CLI) directly:
  client.py ──TCP──► server.py
```

---

## Project Files

```
chat_project/
├── server/
│   └── server.py         ← TCP chat server (run first)
├── client/
│   └── client.py         ← CLI client (optional)
├── web_gui/
│   ├── bridge.py         ← WebSocket-to-TCP bridge
│   └── index.html        ← Web GUI (open in browser)
├── requirements.txt
└── README.md
```

---

## Quick Start

### Step 1 — Install dependencies
```bash
pip install websockets
```

### Step 2 — Start the chat server
```bash
cd server
python server.py
# Output: Chat Server running on 0.0.0.0:9999
```

### Step 3A — Use Web GUI (Recommended)
```bash
cd web_gui
python bridge.py
# Output: Web bridge running on ws://localhost:8765
```
Then open `web_gui/index.html` in your browser.

### Step 3B — Use CLI Client
```bash
cd client
python client.py
# Follow prompts to connect, login/register, and chat
```

---

## Features

| Feature | Details |
|---------|---------|
| **Authentication** | Register / Login with hashed passwords |
| **Group Chat** | Public rooms (#general, etc.) |
| **Private Messaging** | One-to-one DMs |
| **File Sharing** | Send images, docs, any file type |
| **Image Preview** | Images auto-preview in the web GUI |
| **Rooms** | Create and join multiple rooms |
| **Online Users** | Live sidebar showing who's online |
| **File Storage** | Server stores files in `server_uploads/` |

---

## CLI Commands (client.py)

```
<message>              → Send to current room
/pm <user> <msg>       → Private message
/file <path>           → Send file to room
/pmfile <user> <path>  → Send file privately
/join <room>           → Join or create a room
/rooms                 → List all rooms
/users                 → List online users
/quit                  → Exit
```

---

## Network Protocol

All messages are sent as **length-prefixed JSON over TCP**:

```
[4 bytes: message length] [JSON payload]
```

### Message Types

| Type | Direction | Fields |
|------|-----------|--------|
| `login` / `register` | Client→Server | username, password |
| `auth_ok` | Server→Client | username, message |
| `auth_fail` | Server→Client | message |
| `message` | Both | from, room, message, timestamp |
| `private` | Both | from, to, message, timestamp |
| `file` | Both | from, filename, size, data (base64), to? |
| `join_room` | Client→Server | room |
| `room_joined` | Server→Client | room |
| `user_list` | Server→Client | users[] |
| `room_list` | Server→Client | rooms{} |
| `server_notice` | Server→Client | message |

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Server | Python `socket` + `threading` |
| Protocol | TCP (raw sockets) |
| Encoding | Length-prefixed JSON + Base64 (files) |
| Web Bridge | Python `websockets` (asyncio) |
| GUI | Vanilla HTML/CSS/JavaScript |
| Security | SHA-256 password hashing |

---

## Multi-Client Test (Quick Demo)

Terminal 1: `python server/server.py`
Terminal 2: `python web_gui/bridge.py`
Browser 1: Open index.html, Register as "Alice"
Browser 2: Open index.html (new tab), Register as "Bob"

- Alice sends a message → Bob sees it instantly
- Bob uploads a file → Alice can download it
- Either user types `/join dev` → separate room

---

## Concepts Demonstrated

- **TCP Sockets** — `socket.socket(AF_INET, SOCK_STREAM)`
- **Multithreading** — `threading.Thread` per client
- **Synchronization** — `threading.Lock` for shared state
- **Protocol Design** — Custom length-prefixed binary+JSON protocol
- **File Transfer** — Base64 encoding over TCP
- **WebSocket Bridge** — Async bridge between browser and raw TCP
- **Client-Server Architecture** — Centralized message routing

---

*Built for Computer Networks course project.*
