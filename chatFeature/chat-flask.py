import datetime
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

connected_users = {}

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    print(f'Client connected: {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    user_info = connected_users.pop(request.sid, None)
    if user_info:
        emit('user_left', user_info['name'], broadcast=True)
        print(f'User disconnected: {user_info["name"]}')

@socketio.on('set_user')
def handle_set_user(data):
    name = data.get('name', 'Anonymous')
    connected_users[request.sid] = {
        'name': name,
        'address': request.remote_addr
    }
    emit('user_joined', name, broadcast=True)
    emit('user_list', [user['name'] for user in connected_users.values()], broadcast=True)
    print(f'User registered: {name}')

@socketio.on('send_message')
def handle_send_message(message):
    user = connected_users.get(request.sid, {'name': 'Anonymous'})
    message_data = {
        'sender': user['name'],
        'message': message,
        'timestamp': datetime.datetime.now().isoformat()
    }
    emit('new_message', message_data, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)