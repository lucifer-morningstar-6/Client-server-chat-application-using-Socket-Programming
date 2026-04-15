"""
========================================================
  CHAT SERVER  —  server.py
  Run: python server.py
========================================================
"""

import socket, threading, json, sqlite3, os, time, hashlib, random
from datetime import datetime

HOST = "0.0.0.0"
PORT = 5555
BUF  = 4096

clients = {}          # conn -> {username, room}
rooms   = {}          # room_name -> set of conns
lock    = threading.Lock()

# ── DATABASE ────────────────────────────────────────────────
def init_db():
    con = sqlite3.connect("chat_history.db")
    con.execute("""CREATE TABLE IF NOT EXISTS messages
                   (ts TEXT, room TEXT, sender TEXT, msg TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS users
                   (username TEXT PRIMARY KEY, password_hash TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS offline_messages
                   (ts TEXT, sender TEXT, receiver TEXT, msg TEXT)""")
    con.commit(); con.close()

def save_msg(room, sender, msg):
    con = sqlite3.connect("chat_history.db")
    con.execute("INSERT INTO messages VALUES(?,?,?,?)",
                (datetime.now().strftime("%H:%M"), room, sender, msg))
    con.commit(); con.close()

def get_history(room, limit=20):
    con = sqlite3.connect("chat_history.db")
    rows = con.execute(
        "SELECT ts,sender,msg FROM messages WHERE room=? "
        "ORDER BY rowid DESC LIMIT ?", (room, limit)).fetchall()
    con.close()
    return list(reversed(rows))

def register_user(username, password):
    con = sqlite3.connect("chat_history.db")
    cur = con.cursor()
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    try:
        cur.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, pwd_hash))
        con.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    con.close()
    return success

def verify_user(username, password):
    con = sqlite3.connect("chat_history.db")
    cur = con.cursor()
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    res = cur.execute("SELECT 1 FROM users WHERE username=? AND password_hash=?", (username, pwd_hash)).fetchone()
    con.close()
    return res is not None

def save_offline_msg(sender, receiver, msg):
    con = sqlite3.connect("chat_history.db")
    con.execute("INSERT INTO offline_messages VALUES(?,?,?,?)",
                (datetime.now().strftime("%H:%M:%S"), sender, receiver, msg))
    con.commit(); con.close()

def get_offline_messages(receiver):
    con = sqlite3.connect("chat_history.db")
    rows = con.execute("SELECT ts, sender, msg FROM offline_messages WHERE receiver=? ORDER BY rowid ASC", (receiver,)).fetchall()
    con.execute("DELETE FROM offline_messages WHERE receiver=?", (receiver,))
    con.commit(); con.close()
    return rows

# ── HELPERS ─────────────────────────────────────────────────
def send(conn, **kwargs):
    try:
        conn.sendall((json.dumps(kwargs) + "\n").encode())
    except Exception:
        pass

def broadcast(room, exclude=None, **kwargs):
    with lock:
        conns = list(rooms.get(room, set()))
    for c in conns:
        if c is not exclude:
            send(c, **kwargs)

def join_room(conn, new_room):
    uname = clients[conn]["username"]
    old   = clients[conn]["room"]
    with lock:
        if old and old in rooms:
            rooms[old].discard(conn)
        rooms.setdefault(new_room, set()).add(conn)
        clients[conn]["room"] = new_room
    if old and old != new_room:
        broadcast(old, exclude=conn, type="system",
                  msg=f"{uname} left to #{new_room}")
    hist = get_history(new_room)
    if hist:
        send(conn, type="history", room=new_room,
             rows=[{"ts": t, "sender": s, "msg": m} for t, s, m in hist])
    send(conn, type="system", msg=f"You joined #{new_room}")
    broadcast(new_room, exclude=conn, type="system",
              msg=f"{uname} joined #{new_room}")
    with lock:
        users = [clients[c]["username"]
                 for c in rooms.get(new_room, set()) if c in clients]
    broadcast(new_room, type="userlist", users=users)

# ── CLIENT HANDLER ──────────────────────────────────────────
def handle_client(conn, addr):
    print(f"[+] {addr} connected")
    is_authenticated = False
    pending_otp = None
    auth_username = None

    try:
        send(conn, type="auth_required")
        buf = ""
        while True:
            chunk = conn.recv(BUF)
            if not chunk:
                break
            buf += chunk.decode(errors="ignore")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                mtype = data.get("type", "")

                if not is_authenticated:
                    if mtype == "register":
                        u = str(data.get("username", "")).strip()
                        p = str(data.get("password", ""))
                        if not u or not p:
                            send(conn, type="auth_error", msg="Username/password cannot be empty.")
                        elif register_user(u, p):
                            send(conn, type="auth_success", msg="Registration successful. You can now login.")
                        else:
                            send(conn, type="auth_error", msg="Username already taken.")
                    elif mtype == "login":
                        u = str(data.get("username", "")).strip()
                        p = str(data.get("password", ""))
                        if verify_user(u, p):
                            pending_otp = str(random.randint(100000, 999999))
                            auth_username = u
                            print(f"\n{'='*40}\n🔒 SMS SERVER:\nOTP for '{u}': {pending_otp}\n{'='*40}\n")
                            send(conn, type="auth_wait_otp", msg="Enter the 6-digit OTP printed on the server console.")
                        else:
                            send(conn, type="auth_error", msg="Invalid username or password.")
                    elif mtype == "verify_otp":
                        otp = str(data.get("otp", "")).strip()
                        if pending_otp and otp == pending_otp:
                            is_authenticated = True
                            with lock:
                                clients[conn] = {"username": auth_username, "room": None}
                            send(conn, type="welcome", username=auth_username)
                            join_room(conn, "general")
                            
                            off_msgs = get_offline_messages(auth_username)
                            if off_msgs:
                                send(conn, type="system", msg=f"--- You have {len(off_msgs)} offline messages ---")
                                for ts, s, m in off_msgs:
                                    send(conn, type="pm", sender=s, msg=m, ts=ts)
                                send(conn, type="system", msg="--------------------------------------------")
                        else:
                            send(conn, type="auth_error", msg="Invalid OTP.")
                    else:
                        send(conn, type="auth_error", msg="You must be authenticated to do that.")
                    continue

                # Authenticated flow
                room  = clients[conn]["room"]
                uname = clients[conn]["username"]
                mtype = data.get("type", "")

                if mtype == "chat":
                    text = str(data.get("text", ""))[:500]
                    ts   = datetime.now().strftime("%H:%M")
                    if text.startswith("/"):
                        parts = text.split(" ", 1)
                        cmd   = parts[0].lower()
                        arg   = parts[1].strip() if len(parts) > 1 else ""
                        if cmd == "/join":
                            if arg:
                                join_room(conn, arg)
                            else:
                                send(conn, type="system", msg="Usage: /join <room>")
                        elif cmd == "/msg":
                            p2 = arg.split(" ", 1)
                            if len(p2) < 2:
                                send(conn, type="system",
                                     msg="Usage: /msg <username> <message>")
                            else:
                                tname, tmsg = p2
                                with lock:
                                    tc = next((c for c, i in clients.items()
                                               if i["username"] == tname), None)
                                if tc:
                                    send(tc,   type="pm",      sender=uname, msg=tmsg, ts=ts)
                                    send(conn, type="pm_sent", to=tname,     msg=tmsg, ts=ts)
                                else:
                                    # Check if the user exists in DB to save as offline message
                                    con = sqlite3.connect("chat_history.db")
                                    exists = con.execute("SELECT 1 FROM users WHERE username=?", (tname,)).fetchone()
                                    con.close()
                                    if exists:
                                        save_offline_msg(uname, tname, tmsg)
                                        send(conn, type="pm_sent", to=tname, msg=tmsg+" (Offline)", ts=ts)
                                    else:
                                        send(conn, type="system", msg=f"User '{tname}' not found.")
                        elif cmd == "/list":
                            with lock:
                                users = [clients[c]["username"]
                                         for c in rooms.get(room, set()) if c in clients]
                            send(conn, type="userlist", users=users)
                        elif cmd == "/rooms":
                            with lock:
                                rl = {r: len(m) for r, m in rooms.items()}
                            info = ", ".join(f"#{r}({n})" for r, n in rl.items())
                            send(conn, type="system", msg=f"Rooms: {info}")
                        elif cmd == "/history":
                            hist = get_history(room, 30)
                            send(conn, type="history", room=room,
                                 rows=[{"ts": t, "sender": s, "msg": m}
                                       for t, s, m in hist])
                        elif cmd == "/ping":
                            send(conn, type="pong", t=time.time())
                        elif cmd == "/help":
                            send(conn, type="system",
                                 msg=("/join <room>      Join a room\n"
                                      "/msg <user> <m>  Private message\n"
                                      "/list             Users in room\n"
                                      "/rooms            All rooms\n"
                                      "/history          Chat history\n"
                                      "/ping             Latency check\n"
                                      "/help             This help"))
                        elif cmd == "/quit":
                            break
                        else:
                            send(conn, type="system",
                                 msg=f"Unknown command '{cmd}'. Try /help")
                    else:
                        broadcast(room, type="chat", sender=uname, msg=text, ts=ts)
                        save_msg(room, uname, text)

                elif mtype == "ping":
                    send(conn, type="pong", t=time.time())

                elif mtype == "file_meta":
                    fname = str(data.get("name", "file"))[:100]
                    fsize = int(data.get("size", 0))
                    if fsize > 10 * 1024 * 1024:
                        send(conn, type="system", msg="File too large (max 10 MB).")
                        continue
                    send(conn, type="file_ok")
                    received = 0; chunks = []
                    while received < fsize:
                        need  = min(BUF, fsize - received)
                        piece = conn.recv(need)
                        if not piece:
                            break
                        chunks.append(piece); received += len(piece)
                    os.makedirs("received_files", exist_ok=True)
                    safe = "".join(c for c in fname if c.isalnum() or c in "._-")
                    path = os.path.join("received_files", f"{uname}_{safe}")
                    with open(path, "wb") as f:
                        f.write(b"".join(chunks))
                    broadcast(room, type="system",
                              msg=f"📎 {uname} shared '{fname}' ({fsize} bytes)")
                    save_msg(room, uname, f"[FILE] {fname}")

    except Exception as e:
        print(f"[ERR] {clients.get(conn,{}).get('username','?')}: {e}")
    finally:
        uname = clients.get(conn, {}).get("username", "?")
        room  = clients.get(conn, {}).get("room")
        with lock:
            clients.pop(conn, None)
            if room and room in rooms:
                rooms[room].discard(conn)
        if room:
            broadcast(room, type="system", msg=f"{uname} left the chat.")
        try: conn.close()
        except: pass
        print(f"[-] {uname} disconnected")

# ── START ────────────────────────────────────────────────────
def main():
    init_db()
    os.makedirs("received_files", exist_ok=True)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(20)
    print("=" * 44)
    print(f"  Chat Server running on port {PORT}")
    print(f"  Ctrl+C to stop")
    print("=" * 44)
    try:
        while True:
            conn, addr = srv.accept()
            threading.Thread(target=handle_client,
                             args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        srv.close()

if __name__ == "__main__":
    main()
