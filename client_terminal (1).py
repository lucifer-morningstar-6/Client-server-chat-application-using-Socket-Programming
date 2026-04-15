"""
========================================================
  CHAT CLIENT (TERMINAL)  —  client_terminal.py
  Run: python client_terminal.py
  No dependencies — useful for testing multiple clients
========================================================
"""

import socket, threading, json, os, time

HOST_DEFAULT = "127.0.0.1"
PORT_DEFAULT = 5555
BUF = 4096

# ── ANSI COLOURS ────────────────────────────────────────────
R = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
YELLOW = "\033[93m"
MAGENTA= "\033[95m"
RED    = "\033[91m"
GREEN  = "\033[92m"
DIM    = "\033[2m"
BLUE   = "\033[94m"

def pinfo(msg):  print(f"\r{YELLOW}  ℹ  {msg}{R}")
def pchat(ts, sender, msg, me=False):
    c = CYAN if me else BLUE
    print(f"\r{DIM}[{ts}]{R} {c}{BOLD}{sender}{R}: {msg}")
def ppm(msg):    print(f"\r{MAGENTA}  🔒  {msg}{R}")
def perr(msg):   print(f"\r{RED}  ⚠  {msg}{R}")
def psep(msg):   print(f"\r{DIM}  {msg}{R}")

sock     = None
me       = ""
t_ping   = 0.0
alive    = True
auth_state = "initial"

# ── RECEIVE THREAD ──────────────────────────────────────────
def recv_loop():
    global alive
    buf = ""
    while alive:
        try:
            data = sock.recv(BUF)
            if not data: break
            buf += data.decode(errors="ignore")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
                if line:
                    try: handle(json.loads(line))
                    except: pass
        except OSError: break
    alive = False
    perr("Disconnected from server.")

def handle(p):
    global t_ping, auth_state
    t = p.get("type","")

    if t == "auth_required":
        auth_state = "menu"
        print("\n\r=== AUTHENTICATION ===")
        print("\r[1] Login")
        print("\r[2] Register")
        print("\r> ", end="", flush=True)

    elif t == "auth_wait_otp":
        auth_state = "otp"
        pinfo(p.get("msg", "OTP required"))
        print("\rOTP> ", end="", flush=True)

    elif t == "auth_error":
        perr(p.get("msg", "Error"))
        if auth_state == "menu":
            print("\r[1] Login\n\r[2] Register\n\r> ", end="", flush=True)

    elif t == "auth_success":
        pinfo(p.get("msg", "Success"))
        if auth_state == "menu":
            print("\r[1] Login\n\r[2] Register\n\r> ", end="", flush=True)

    elif t == "welcome" or t == "system":
        if t == "welcome":
            auth_state = "chat"
        pinfo(p.get("msg", p.get("username","")))



    elif t == "chat":
        sender = p.get("sender","?")
        pchat(p.get("ts","--"), sender, p.get("msg",""), sender==me)

    elif t == "pm":
        ppm(f"PM from {p['sender']}: {p['msg']}")

    elif t == "pm_sent":
        ppm(f"PM → {p['to']}: {p['msg']}")

    elif t == "history":
        psep(f"── history: #{p.get('room','?')} ──")
        for r in p.get("rows",[]):
            pchat(r.get("ts","--"), r.get("sender","?"), r.get("msg",""))
        psep("── end of history ──")

    elif t == "userlist":
        pinfo("Online: " + ", ".join(p.get("users",[])))

    elif t == "pong":
        ms = round((time.time()-t_ping)*1000,1)
        pinfo(f"Pong!  {ms} ms latency")

def send_raw(obj):
    try: sock.sendall((json.dumps(obj)+"\n").encode())
    except Exception as e: perr(f"Send error: {e}")

def send_file(path):
    name = os.path.basename(path)
    size = os.path.getsize(path)
    send_raw({"type":"file_meta","name":name,"size":size})
    time.sleep(0.4)
    with open(path,"rb") as f:
        while chunk := f.read(BUF):
            try: sock.sendall(chunk)
            except: break
    pinfo(f"'{name}' sent.")

# ── MAIN ────────────────────────────────────────────────────
def main():
    global sock, me, t_ping, alive

    host = input(f"Server IP [{HOST_DEFAULT}]: ").strip() or HOST_DEFAULT
    raw  = input(f"Port [{PORT_DEFAULT}]: ").strip()
    port = int(raw) if raw else PORT_DEFAULT

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((host, port))
    except Exception as e:
        perr(f"Cannot connect: {e}"); return

    pinfo(f"Connected to {host}:{port}")
    pinfo("Type a message and press Enter.")
    pinfo("Commands: /join <room>  /msg <user> <text>  /list  /rooms  /history  /ping  /help  /quit")
    pinfo("To send a file type:  !file /path/to/file")

    threading.Thread(target=recv_loop, daemon=True).start()

    while alive:
        try:
            text = input()
        except (EOFError, KeyboardInterrupt):
            break

        text = text.strip()
        if not text: continue

        if auth_state == "menu":
            if text == "1":
                u = input("Username: ")
                p = input("Password: ")
                send_raw({"type": "login", "username": u, "password": p})
            elif text == "2":
                u = input("New Username: ")
                p = input("New Password: ")
                send_raw({"type": "register", "username": u, "password": p})
            else:
                print("Invalid choice.")
                print("\r> ", end="", flush=True)
        elif auth_state == "otp":
            send_raw({"type": "verify_otp", "otp": text})
        elif auth_state == "chat":
            if text.startswith("!file "):
                path = text[6:].strip()
                if os.path.isfile(path):
                    threading.Thread(target=send_file, args=(path,), daemon=True).start()
                else:
                    perr("File not found.")
            elif text.lower() in ("/quit","exit","quit"):
                break
            elif text == "/ping":
                t_ping = time.time()
                send_raw({"type":"ping"})
            else:
                send_raw({"type":"chat","text":text})

    alive = False
    try: sock.close()
    except: pass
    print("Bye!")

if __name__ == "__main__":
    main()
