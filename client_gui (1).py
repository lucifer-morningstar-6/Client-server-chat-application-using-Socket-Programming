"""
========================================================
  CHAT CLIENT  —  client_gui.py
  Run: python client_gui.py
  Requires: Python 3.8+  (no extra pip installs)
========================================================
"""

import socket, threading, json, os, time
import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog, simpledialog

HOST_DEFAULT = "127.0.0.1"
PORT_DEFAULT = 5555
BUF = 4096

# ── COLOURS ─────────────────────────────────────────────────
BG      = "#1a1b2e"
PANEL   = "#16213e"
INPUT   = "#0f3460"
ACCENT  = "#e94560"
ACCENTL = "#ff6b81"
TEXT    = "#eaeaea"
DIM     = "#7f8c8d"
SYS     = "#f39c12"
PM      = "#9b59b6"
TS      = "#5d6d7e"


class App:
    def __init__(self, root):
        self.root   = root
        self.sock   = None
        self.me     = ""
        self.room   = "general"
        self.alive  = False
        self.t_ping = 0.0
        self._history = []
        self._hidx    = -1

        root.title("ChatApp")
        root.configure(bg=BG)
        root.geometry("960x640")
        root.minsize(720, 480)
        root.protocol("WM_DELETE_WINDOW", self._quit)

        self._build_ui()
        # Show connect dialog after the main window is ready
        root.after(100, self._connect_dialog)

    # ────────────────────────────────────────────────────────
    # UI BUILD
    # ────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── top bar ──
        top = tk.Frame(self.root, bg=ACCENT, height=44)
        top.pack(fill=tk.X)
        top.pack_propagate(False)

        tk.Label(top, text="💬  ChatApp",
                 font=("Arial", 14, "bold"), bg=ACCENT, fg="white"
                 ).pack(side=tk.LEFT, padx=12)

        self.lbl_status = tk.Label(top, text="● Disconnected",
                                   font=("Arial", 10), bg=ACCENT, fg="#ffaaaa")
        self.lbl_status.pack(side=tk.RIGHT, padx=12)

        self.lbl_ping = tk.Label(top, text="", font=("Arial", 9),
                                 bg=ACCENT, fg="white")
        self.lbl_ping.pack(side=tk.RIGHT, padx=6)

        self.lbl_room = tk.Label(top, text="", font=("Arial", 10),
                                 bg=ACCENT, fg="white")
        self.lbl_room.pack(side=tk.RIGHT, padx=10)

        # ── body ──
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill=tk.BOTH, expand=True)

        # ── sidebar ──
        side = tk.Frame(body, bg=PANEL, width=178)
        side.pack(side=tk.LEFT, fill=tk.Y, padx=(4, 0), pady=4)
        side.pack_propagate(False)

        tk.Label(side, text="ROOM", bg=PANEL, fg=DIM,
                 font=("Arial", 8, "bold")).pack(anchor="w", padx=8, pady=(10, 2))

        rf = tk.Frame(side, bg=PANEL)
        rf.pack(fill=tk.X, padx=6)
        self.room_var = tk.StringVar(value="general")
        self.room_ent = tk.Entry(rf, textvariable=self.room_var,
                                 bg=INPUT, fg=TEXT, insertbackground=TEXT,
                                 font=("Arial", 10), relief=tk.FLAT)
        self.room_ent.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        self.room_ent.bind("<Return>", lambda e: self._join())
        tk.Button(rf, text="Go", bg=ACCENT, fg="white", font=("Arial", 9),
                  relief=tk.FLAT, cursor="hand2", command=self._join
                  ).pack(side=tk.RIGHT, ipady=3, ipadx=6)

        tk.Label(side, text="USERS ONLINE", bg=PANEL, fg=DIM,
                 font=("Arial", 8, "bold")).pack(anchor="w", padx=8, pady=(14, 2))

        self.user_lb = tk.Listbox(side, bg=INPUT, fg=TEXT,
                                  selectbackground=ACCENT,
                                  font=("Arial", 10), relief=tk.FLAT,
                                  bd=0, activestyle="none")
        self.user_lb.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 2))
        self.user_lb.bind("<Double-Button-1>", self._pm_click)
        tk.Label(side, text="double-click → DM", bg=PANEL, fg=DIM,
                 font=("Arial", 8)).pack(pady=(0, 6))

        for label, cmd in [("📎 Send File", self._send_file),
                           ("📜 History",   lambda: self._cmd("/history")),
                           ("📡 Ping",      self._ping),
                           ("❓ Help",      lambda: self._cmd("/help"))]:
            tk.Button(side, text=label, bg=INPUT, fg=TEXT, font=("Arial", 10),
                      relief=tk.FLAT, cursor="hand2", command=cmd
                      ).pack(fill=tk.X, padx=6, pady=2, ipady=4)

        # ── chat pane ──
        chat = tk.Frame(body, bg=BG)
        chat.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.display = scrolledtext.ScrolledText(
            chat, state=tk.DISABLED, wrap=tk.WORD,
            bg=BG, fg=TEXT, font=("Arial", 11),
            relief=tk.FLAT, bd=0, padx=6, pady=4)
        self.display.pack(fill=tk.BOTH, expand=True)

        self.display.tag_config("ts",    foreground=TS,       font=("Arial", 9))
        self.display.tag_config("me",    foreground=ACCENTL,  font=("Arial", 11, "bold"))
        self.display.tag_config("other", foreground="#5dade2", font=("Arial", 11, "bold"))
        self.display.tag_config("sys",   foreground=SYS,      font=("Arial", 10, "italic"))
        self.display.tag_config("pm",    foreground=PM,       font=("Arial", 11, "bold"))
        self.display.tag_config("err",   foreground="#e74c3c")
        self.display.tag_config("sep",   foreground=DIM)
        self.display.tag_config("body",  foreground=TEXT)

        # ── input bar ──
        bar = tk.Frame(chat, bg=PANEL, pady=4)
        bar.pack(fill=tk.X)

        self.inp = tk.Entry(bar, bg=INPUT, fg=TEXT, insertbackground=TEXT,
                            font=("Arial", 12), relief=tk.FLAT)
        self.inp.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=7, padx=(8, 4))
        self.inp.bind("<Return>", self._send)
        self.inp.bind("<Up>",     self._hist_up)
        self.inp.bind("<Down>",   self._hist_down)

        tk.Button(bar, text="Send ➤", bg=ACCENT, fg="white",
                  font=("Arial", 11, "bold"), relief=tk.FLAT, cursor="hand2",
                  command=self._send
                  ).pack(side=tk.RIGHT, padx=(0, 8), ipady=6, ipadx=12)

    # ────────────────────────────────────────────────────────
    # CONNECTION DIALOG
    # ────────────────────────────────────────────────────────
    def _connect_dialog(self):
        self.dlg = tk.Toplevel(self.root)
        self.dlg.title("Authentication")
        self.dlg.geometry("340x350")
        self.dlg.configure(bg=BG)
        self.dlg.resizable(False, False)
        self.dlg.grab_set()
        self.dlg.focus_set()

        tk.Label(self.dlg, text="💬  ChatApp WhatsApp Clone",
                 font=("Arial", 15, "bold"), bg=BG, fg=ACCENTL
                 ).pack(pady=(18, 8))

        frm = tk.Frame(self.dlg, bg=BG)
        frm.pack(fill=tk.X, padx=28)

        self._entries = {}
        for lbl, default, show in [("Server IP", HOST_DEFAULT, ""),
                                   ("Port",      str(PORT_DEFAULT), ""),
                                   ("Username",  "", ""),
                                   ("Password",  "", "*")]:
            tk.Label(frm, text=lbl, bg=BG, fg=TEXT, font=("Arial", 10)).pack(anchor="w")
            e = tk.Entry(frm, bg=INPUT, fg=TEXT, insertbackground=TEXT, font=("Arial", 11), relief=tk.FLAT, show=show)
            e.insert(0, default)
            e.pack(fill=tk.X, ipady=4, pady=(0, 5))
            self._entries[lbl] = e

        btn_frm = tk.Frame(self.dlg, bg=BG)
        btn_frm.pack(pady=10)

        def do_auth(mode):
            ip   = self._entries["Server IP"].get().strip() or HOST_DEFAULT
            try: port = int(self._entries["Port"].get().strip())
            except ValueError: port = PORT_DEFAULT
            u = self._entries["Username"].get().strip()
            p = self._entries["Password"].get()
            if not u or not p:
                messagebox.showerror("Error", "Username and Password are required.", parent=self.dlg)
                return
            
            self._pending_auth = {"type": mode, "username": u, "password": p}
            if not self.alive:
                self._connect(ip, port)
            elif self.sock:
                self._send_raw(self._pending_auth)

        tk.Button(btn_frm, text="Login", bg=ACCENT, fg="white", font=("Arial", 11, "bold"), relief=tk.FLAT, cursor="hand2", command=lambda: do_auth("login")).pack(side=tk.LEFT, padx=5, ipady=4, ipadx=10)
        tk.Button(btn_frm, text="Register", bg=DIM, fg="white", font=("Arial", 11, "bold"), relief=tk.FLAT, cursor="hand2", command=lambda: do_auth("register")).pack(side=tk.LEFT, padx=5, ipady=4, ipadx=10)

        self._entries["Password"].bind("<Return>", lambda e: do_auth("login"))
        self._entries["Username"].focus_set()

    # ────────────────────────────────────────────────────────
    # CONNECT
    # ────────────────────────────────────────────────────────
    def _connect(self, host, port):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5)
            self.sock.connect((host, port))
            self.sock.settimeout(None)   # back to blocking
            self.alive = True
            threading.Thread(target=self._recv_loop, daemon=True).start()
        except Exception as e:
            messagebox.showerror("Connection Failed",
                                 f"Could not connect to {host}:{port}\n\n{e}")

    def _quit(self):
        self.alive = False
        try:
            self.sock.close()
        except Exception:
            pass
        self.root.destroy()

    # ────────────────────────────────────────────────────────
    # RECEIVE LOOP  (background thread)
    # ────────────────────────────────────────────────────────
    def _recv_loop(self):
        buf = ""
        while self.alive:
            try:
                data = self.sock.recv(BUF)
                if not data:
                    break
                buf += data.decode(errors="ignore")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line:
                        try:
                            pkt = json.loads(line)
                            self.root.after(0, self._handle, pkt)
                        except json.JSONDecodeError:
                            pass
            except OSError:
                break
        self.alive = False
        self.root.after(0, lambda: self.lbl_status.config(
            text="● Disconnected", fg="#ffaaaa"))
        self.root.after(0, self._sys, "⚠  Disconnected from server.")

    # ────────────────────────────────────────────────────────
    # PACKET HANDLER  (runs on main thread via root.after)
    # ────────────────────────────────────────────────────────
    def _handle(self, p):
        t = p.get("type", "")

        if t == "auth_required":
            if hasattr(self, '_pending_auth') and self._pending_auth:
                self._send_raw(self._pending_auth)
                
        elif t == "auth_error":
            messagebox.showerror("Auth Error", p.get("msg", "Error"))
            self._pending_auth = None
            
        elif t == "auth_success":
            messagebox.showinfo("Success", p.get("msg", "Success"))
            self._pending_auth = None
            
        elif t == "auth_wait_otp":
            otp = simpledialog.askstring("2FA OTP", p.get("msg", "Enter OTP:"))
            if otp:
                self._send_raw({"type": "verify_otp", "otp": otp})
            else:
                self._send_raw({"type": "verify_otp", "otp": ""})

        elif t == "welcome":
            self.me = p.get('username', 'Guest')
            if hasattr(self, 'dlg') and self.dlg and self.dlg.winfo_exists():
                self.dlg.destroy()
            self.lbl_status.config(text="● Connected", fg="#aaffaa")
            self.root.title(f"WhatsApp Clone — {self.me}")
            self.inp.focus_set()
            self._sys(f"✅  Welcome, {self.me}!")

        elif t == "chat":
            sender = p.get("sender", "?")
            tag    = "me" if sender == self.me else "other"
            self._chat(p.get("ts", "--:--"), sender, p.get("msg", ""), tag)

        elif t == "system":
            self._sys(p.get("msg", ""))

        elif t == "pm":
            self._pm(f"🔒 PM from {p['sender']}: {p['msg']}")

        elif t == "pm_sent":
            self._pm(f"🔒 PM → {p['to']}: {p['msg']}")

        elif t == "history":
            self._sep(f"── history: #{p.get('room', '?')} ──")
            for r in p.get("rows", []):
                self._chat(r.get("ts", "--"), r.get("sender", "?"),
                           r.get("msg", ""), "other")
            self._sep("── end of history ──")

        elif t == "userlist":
            users = p.get("users", [])
            self.user_lb.delete(0, tk.END)
            for u in users:
                self.user_lb.insert(tk.END, f"🟢  {u}")
            self.lbl_room.config(text=f"#{self.room}  ({len(users)} online)")

        elif t == "pong":
            ms = round((time.time() - self.t_ping) * 1000, 1)
            self.lbl_ping.config(text=f"🏓 {ms} ms")
            self._sys(f"Pong!  {ms} ms latency")

        elif t == "file_ok":
            pass   # file bytes are sent right after in _send_file thread

    # ────────────────────────────────────────────────────────
    # SEND HELPERS
    # ────────────────────────────────────────────────────────
    def _send(self, _=None):
        txt = self.inp.get().strip()
        if not txt or not self.alive:
            return
        self._history.insert(0, txt)
        self._hidx = -1
        self.inp.delete(0, tk.END)
        self._send_raw({"type": "chat", "text": txt})

    def _send_raw(self, obj):
        try:
            self.sock.sendall((json.dumps(obj) + "\n").encode())
        except Exception as e:
            self.root.after(0, self._err, f"Send error: {e}")

    def _cmd(self, text):
        if self.alive:
            self._send_raw({"type": "chat", "text": text})

    def _join(self):
        r = self.room_var.get().strip()
        if r:
            self.room = r
            self._cmd(f"/join {r}")

    def _ping(self):
        self.t_ping = time.time()
        self._send_raw({"type": "ping"})

    def _pm_click(self, _=None):
        sel = self.user_lb.curselection()
        if not sel:
            return
        target = self.user_lb.get(sel[0]).replace("🟢  ", "").strip()
        if target == self.me:
            return
        msg = simpledialog.askstring(
            "Private Message", f"Message to {target}:", parent=self.root)
        if msg:
            self._cmd(f"/msg {target} {msg}")

    def _send_file(self):
        if not self.alive:
            messagebox.showinfo("Not connected", "Connect to the server first.")
            return
        path = filedialog.askopenfilename(title="Choose a file to send",
                                          parent=self.root)
        if not path:
            return
        name = os.path.basename(path)
        size = os.path.getsize(path)
        if size > 10 * 1024 * 1024:
            messagebox.showwarning("Too large", "Max file size is 10 MB.")
            return
        self._send_raw({"type": "file_meta", "name": name, "size": size})

        def upload():
            time.sleep(0.4)   # give server a moment to send file_ok
            try:
                with open(path, "rb") as f:
                    while chunk := f.read(BUF):
                        self.sock.sendall(chunk)
                self.root.after(0, self._sys, f"✅  '{name}' uploaded successfully.")
            except Exception as e:
                self.root.after(0, self._err, f"Upload failed: {e}")

        threading.Thread(target=upload, daemon=True).start()

    def _hist_up(self, _=None):
        if self._history:
            self._hidx = min(self._hidx + 1, len(self._history) - 1)
            self.inp.delete(0, tk.END)
            self.inp.insert(0, self._history[self._hidx])

    def _hist_down(self, _=None):
        if self._hidx > 0:
            self._hidx -= 1
            self.inp.delete(0, tk.END)
            self.inp.insert(0, self._history[self._hidx])
        else:
            self._hidx = -1
            self.inp.delete(0, tk.END)

    # ────────────────────────────────────────────────────────
    # DISPLAY HELPERS  (always called on main thread)
    # ────────────────────────────────────────────────────────
    def _write(self, *pairs):
        self.display.config(state=tk.NORMAL)
        for text, tag in pairs:
            self.display.insert(tk.END, text, tag)
        self.display.see(tk.END)
        self.display.config(state=tk.DISABLED)

    def _chat(self, ts, sender, msg, tag):
        self._write(
            (f"[{ts}] ", "ts"),
            (f"{sender}: ", tag),
            (f"{msg}\n", "body"))

    def _sys(self, msg):
        self._write((f"  {msg}\n", "sys"))

    def _pm(self, msg):
        self._write((f"  {msg}\n", "pm"))

    def _err(self, msg):
        self._write((f"  ⚠  {msg}\n", "err"))

    def _sep(self, msg):
        self._write((f"\n  {msg}\n\n", "sep"))


# ── ENTRY POINT ─────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
