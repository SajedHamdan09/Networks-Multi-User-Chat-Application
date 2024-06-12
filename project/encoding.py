from flask import Flask, request, render_template, redirect, url_for, session
# flask_socketio controls the WebSocket connections, usually initialized with the Flask app
from flask_socketio import SocketIO, join_room, leave_room, send
from scapy.all import IP, TCP, Raw, send as scapy_send
from pyldpc import encode, decode, get_message
from cryptography.fernet import Fernet
import string
import random

app = Flask(__name__)
# securing cookies session
app.config['SECRET_KEY'] = 'SDKFJSDFOWEIOF'
# initialized with the app
socketio = SocketIO(app, async_mode='threading')


#storing the rooms' code for all chat rooms created
rooms = {}

# Define LDPC code parameters
n = 15
d_v = 3
d_c = 6
H, G = get_message(n, d_v, d_c, systematic=True)

# Generate a secret key for encryption and decryption
secret_key = Fernet.generate_key()
cipher_suite = Fernet(secret_key)

# Encrypt a message
def encrypt_message(message):
    return cipher_suite.encrypt(message.encode())

# Decrypt a message
def decrypt_message(encrypted_message):
    return cipher_suite.decrypt(encrypted_message).decode()

# Function to encode messages
def channel_encode(message):
    return encode(message, G)

# Function to decode received messages
def channel_decode(received):
    return decode(received, H, algorithm='minsum')


#creating chat room code, either using ascii_letters or uuid, but the UUID will be a large code since it consists of 36 characters

# def generate_room_code():
#     return str(uuid.uuid4())
def generate_room_code(existing_codes: list[str]) -> str:
    # for i in range(6):
        code_chars = [random.choice(string.ascii_letters) for _ in range(4)]
        code = ''.join(code_chars)

        if code not in existing_codes:
            return code


# GET is used to retrieve data from the server
# POST enables the user to send data over to the server
@app.route('/', methods=["GET", "POST"])
def home():
    session.clear()

    # this indicates that the user has submitted a form (POST method), and then I retrive the submissions of the user
    if request.method == "POST":
        name = request.form.get('name')
        create = request.form.get('create', False)
        code = request.form.get('code')
        join = request.form.get('join', False)

        # if not name, user has no name entered
        if not name:
            return render_template('home.html', error="Please Enter Name", code=code)
      
        # checking if the user is requesting to create a chat
        if create != False:
            # the list(rooms.keys()) code creates a list containing the keys of the available rooms, so that the code will be unique for every chat
            room_code = generate_room_code(list(rooms.keys()))
            
            # create a new room and then add that new room to the defined map that contains all created rooms, stroing their info            
            new_room = {'members': 0, 'messages': []}
            rooms[room_code] = new_room

       # checking if the user is requesting to join a chat
        if join != False:
            # if user didnt enter a chat code
            if not code:
                return render_template('home.html', error="Please enter the room code to join the chat", name=name)
            # if user entered wrong or invalid code
            if code not in rooms:
                return render_template('home.html', error="Room code invalid, Room code not found", name=name)
            room_code = code

        # the next time the user makes a request, the server can retrieve the users name from the session
        session['room'] = 111
        session['name'] = name

        #  this code is used in web applications built using (Flask), a web framework for Python.
        # so the user accesses a route in the web application by redirecting the user to another page
        return redirect(url_for('room'))
    else:
        # this code is also used in Flask applications and whic allows user to render an HTML template and return it as the response based on the the client's request
        return render_template('home.html')



#this route is called when the user joins a chat
@app.route('/room')
def room():

    # remembering the information about the user between different requests, which are already stored in session
    chat_code = session.get('room')
    name = session.get('name')

    # if the username or room are null when retrived from session then the user will stay on the home page
    # else if the room is not found in the stored rooms then room does not exist to join
    if name is None or chat_code is None or chat_code not in rooms:
        return redirect(url_for('home'))
    
    
    # define a variable that retrives the messages of the chat being joined, then the user joins that chat room
    messages = rooms[chat_code]['messages']


    #renders 'room.html' page , and passes variables to it
    return render_template('room.html', room=chat_code, user=name, messages=messages)



@socketio.on('connect')
def handle_connect():

    # retriving users info from session
    name = session.get('name')
    chat_code = session.get('room')

    
    # checking if the name or room are null, or wether room does not exist
    if name is None or chat_code is None:
        return
    if room not in rooms:
        leave_room(chat_code)

    # this is called to subscribe the connected user to a chat room, adding the user to the specified room
    # then a message is sent to all members of that room using the send function notifying them that a new user has joined 
    join_room(chat_code)
    send({
        "sender": "",
        "message": f"{name} entered the chat"
    }, to=chat_code)
    rooms[chat_code]["members"] += 1





# payload is the data sent by the client
@socketio.on('message')
def handle_message(payload):
    
     # retriving users info from session
    room = session.get('room')
    name = session.get('name')
    
    if room not in rooms:
        return send({"error": "Room not found"}, to=request.sid)
    
    # Encrypt the message before sending
    encrypted_message = encrypt_message(payload["message"])
    message = {"sender": name, "message": encrypted_message}
    
    # Get the user's IP address
    src_ip = request.remote_addr
    
    # Send the message packet with the user's IP address
    send_packet(message, src_ip)
    
    rooms[room]["messages"].append(message)
    
    # Receive packet from the network
    received_packet = receive_packet()  
    if received_packet:
        if validate_checksum(received_packet):
            print("Checksum is valid. Packet integrity maintained.")
            try:
                # Decrypt the received message
                decrypted_message = decrypt_message(received_packet["message"])
                print("Decrypted message:", decrypted_message)
                message = {"sender": "Server", "message": decrypted_message}
                send(message, to=room)
                rooms[room]["messages"].append(message)
            except Exception as e:
                print("Decryption error:", str(e))
        else:
            print("Checksum mismatch. Packet integrity compromised.")
            # Retry mechanism on sender's side
            retry_count = 0
            while retry_count < 3:  # Retry for a maximum of 3 times
                retry_count += 1
                print(f"Retrying... Attempt {retry_count}")
                time.sleep(1)  # Wait for a short duration before retrying
                send_packet(payload["message"], request.remote_addr)
                # Check if a new packet is received after retry
                received_packet = receive_packet()
                if received_packet and validate_checksum(received_packet):
                    print("Retry successful. Packet received.")
                    break
            else:
                # If retries fail, request sender to resend the packet
                print("Retries failed. Requesting sender to resend.")
                send({"error": "Checksum mismatch. Please resend the packet."}, to=room)
    else:
        print("No packet received.")


# event handler for the ‘disconnect’ event when a ‘disconnect’ event is received from a client side
@socketio.on('disconnect')
def handle_disconnect():
    # retriving users info from session
    room = session.get("room")
    name = session.get("name")
    leave_room(room)

    # if room exists, decrement number of user from the chat, and if chat has no more users then delete chat 
    if room in rooms:
        rooms[room]["members"] -= 1
        if rooms[room]["members"] <= 0:
            del rooms[room]

    # this sends a message to all clients connected to the chat that the user has left the chat room
    send({
        "message": f"{name} left the chat ",
        "sender": ""
    }, to=room)


def send_packet(message, src_ip):
    dst_ip = "10.0.0.33"  # Replace with your server's IP
    dst_port = 5000
    raw_data = str(message).encode('utf-8')  # Encode message to bytes
    
    # Calculate checksum for the packet
    packet_without_checksum = IP(src=src_ip, dst=dst_ip) / TCP(dport=dst_port) / Raw(load=raw_data)
    checksum = packet_without_checksum.__class__(bytes(packet_without_checksum)).chksum
    
    # Create the packet with the calculated checksum
    packet = IP(src=src_ip, dst=dst_ip, chksum=checksum) / TCP(dport=dst_port, sport=12345) / Raw(load=raw_data)  # Replace 12345 with your desired source port
    scapy_send(packet)

def validate_checksum(packet):
    # Assuming packet is a scapy packet object
    return packet and packet[IP].chksum == packet[IP].__class__(bytes(packet))

# Function to receive packet
def receive_packet():
    # Logic to receive packet
    packet = None  # Placeholder for received packet
    return packet

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
