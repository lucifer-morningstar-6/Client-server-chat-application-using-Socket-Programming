import socket
import threading
import sys

def receive_messages(client):
    while True:
        try:
            message = client.recv(1024).decode('utf-8')
            if message:
                print(message, end='')
            else:
                break
        except:
            print("\n❌ Connection to server lost.")
            break

# ================== CONNECT TO SERVER ==================
HOST = input("Enter Server IP (e.g. 192.168.1.105): ").strip() or "127.0.0.1"
PORT = 55555

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    client.connect((HOST, PORT))
    print("✅ Connected to server!")
except:
    print("❌ Could not connect. Check IP and that server is running.")
    sys.exit()

# Receive thread
thread = threading.Thread(target=receive_messages, args=(client,))
thread.daemon = True
thread.start()

print("Type messages or commands (/help for list of commands)")
while True:
    try:
        message = input("")
        if message.lower() in ['exit', 'quit']:
            break
        client.send(message.encode('utf-8'))
    except:
        break

client.close()