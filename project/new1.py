import asyncio
import random
from string import ascii_letters
import time
from flask import Flask, request, render_template, redirect, url_for, session
from flask_socketio import SocketIO, join_room, leave_room, send
from bitarray import bitarray
from cryptography.fernet import Fernet
import socket
import base64


app = Flask(__name__)
app.config['SECRET_KEY'] = 'SDKFJSDFOWEIOF'
socketio = SocketIO(app, async_mode='threading')
rooms = {}

def generate_room_code(existing_codes: list) -> str:
    code_chars = [random.choice(ascii_letters) for _ in range(6)]
    code = ''.join(code_chars)
    if code not in existing_codes:
        return code

secret_key = Fernet.generate_key()
cipher_suite = Fernet(secret_key)

def encrypt_message(message):
    return cipher_suite.encrypt(message.encode())

def decrypt_message(encrypted_message):
    return cipher_suite.decrypt(encrypted_message).decode()

def channel_encode(message):
    b = bitarray()
    b.frombytes(message)
    return b

def channel_decode(received):
    return received.tobytes().decode('utf-8')

@app.route('/', methods=["GET", "POST"])
def home():
    session.clear()
    if request.method == "POST":
        name = request.form.get('name')
        create = request.form.get('create', False)
        code = request.form.get('code')
        join = request.form.get('join', False)

        if not name:
            return render_template('home.html', error="Please Enter Name", code=code)
        
        if create != False:
            room_code = generate_room_code(list(rooms.keys()))
            new_room = {'members': 0, 'messages': []}
            rooms[room_code] = new_room

        if join != False:
            if not code:
                return render_template('home.html', error="Please enter the room code to join the chat", name=name)
            if code not in rooms:
                return render_template('home.html', error="Room code invalid, Room code not found", name=name)
            room_code = code

        session['room'] = room_code
        session['name'] = name

        return redirect(url_for('room'))
    else:
        return render_template('home.html')

@app.route('/room')
def room():
    chat_code = session.get('room')
    name = session.get('name')
    if name is None or chat_code is None or chat_code not in rooms:
        return redirect(url_for('home'))
    
    messages = rooms[chat_code]['messages']
    return render_template('room.html', room=chat_code, user=name, messages=messages)

async def async_socketio_handler(f, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, f, *args, **kwargs)

@socketio.on('connect')
def handle_connect():
    name = session.get('name')
    chat_code = session.get('room')
    if name is None or chat_code is None:
        return
    if chat_code not in rooms:
        leave_room(chat_code)
        return send({"error": "Room not found"}, to=request.sid)
    join_room(chat_code)
    send({"sender": "", "message": f"{name} entered the chat"}, to=chat_code)
    rooms[chat_code]["members"] += 1

@socketio.on('message')
def handle_message(payload):
    room = session.get('room')
    name = session.get('name')
    if room not in rooms:
        return send({"error": "Room not found"}, to=request.sid)

    original_message = payload["message"]
    encrypted_message = encrypt_message(original_message)
    encoded_message = base64.b64encode(encrypted_message).decode('utf-8')

    message = {"sender": name, "message": encoded_message}

    print(f"Encoded message: {encoded_message}")

    send_packet(message)

    rooms[room]["messages"].append(message)

    print(f"Message appended to room {room}: {message}")

    # Send the message to the room
    send(message, to=room)





@socketio.on('disconnect')
def handle_disconnect():
    room = session.get("room")
    name = session.get("name")
    leave_room(room)
    if room in rooms:
        rooms[room]["members"] -= 1
        if rooms[room]["members"] <= 0:
            del rooms[room]
    send({"message": f"{name} left the chat ", "sender": ""}, to=room)

def send_packet(message):
    dst_ip = "10.0.0.33"  # Replace with your server's IP
    dst_port = 5000
    raw_data = str(message).encode('utf-8')

    print(f"Sending raw data: {raw_data}")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(raw_data, (dst_ip, dst_port))

    print("Packet sent")

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
