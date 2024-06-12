from flask import Flask, request, render_template, redirect, url_for, session
# flask_socketio controls the WebSocket connections, usually initialized with the Flask app
from flask_socketio import SocketIO, join_room, leave_room, send
import asyncio
from string import ascii_letters
import random
import uuid


app = Flask(__name__)
# securing cookies session
app.config['SECRET_KEY'] = 'SDKFJSDFOWEIOF'
# initialized with the app
socketio = SocketIO(app, async_mode='threading')


#storing the rooms' code for all chat rooms created
rooms = {}


#creating chat room code, either using ascii_letters or uuid, but the UUID will be a large code since it consists of 36 characters

# def generate_room_code():
#     return str(uuid.uuid4())

def generate_room_code(existing_codes: list[str]) -> str:
    # for i in range(6):
        code_chars = [random.choice(ascii_letters) for _ in range(6)]
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
            new_room = {
                'members': 0,
                'messages': []
            }
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
        session['room'] = room_code
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




# this function allows multiple tasks at once without waiting for each other, (async def) so the function is asynchronous
# (f) is the function to be run asynchronously, (*args and **kwargs) allow to pass any number of positional and keyword arguments to the function
# (asyncio.get_running_loop()) is to manage asynchronous tasks.
# loop.run_in_executor(None, f, *args, **kwargs), runs function f asynchronously using the event loop's executor, without tasks blocking eahc other
# (await) allows the asynchronous task to finish and before returning the result.
async def async_socketio_handler(f, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, f, *args, **kwargs)



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



# (handle_connect_async) is also and asynchronous handler for connecting users to a chat room
# this function is asynchronous, meaning it can perform tasks independently, likewise in the code above
# async def handle_connect_async():

#     #retriving username and chat_code from session
#     name = session.get('name')
#     chat_code = session.get('room')

#     # if user or chat_code do not exist, then stop excution 
#     if name is None or chat_code is None:
#         return
    
#     # makes the user leave the chat
#     if chat_code not in rooms:
#         leave_room(chat_code)

#     # allows user to join a chat
#     join_room(chat_code)

#     # allows to send a message to the room saying that user entered chat
#     await send({
#         "sender": "",
#         "message": f"{name} entered the chat"
#     }, to=chat_code)
#     rooms[chat_code]["members"] += 1



# payload is the data sent by the client
@socketio.on('message')
def handle_message(payload):
    # retriving users info from session
    room = session.get('room')
    name = session.get('name')


    # checking if room does exist
    if room not in rooms:
        return
    
    # defining message content
    message = {
        "sender": name,
        "message": payload["message"]
    }

    # sending message to all clients connected to the chat
    send(message, to=room)
    
    # adding the message sent to the message content of the room defined in the list of rooms 
    rooms[room]["messages"].append(message)



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



if __name__ == '__main__':
    socketio.run(app, debug=True)
