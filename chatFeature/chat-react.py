from flask import Flask, request
from flask_socketio import SocketIO, emit, disconnect
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

connected_users = {}

@socketio.on('connect')
def handle_connect():
    print(f'Client connected: {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    user_info = connected_users.pop(request.sid, None)
    if user_info:
        emit('user_left', {'id': request.sid, 'name': user_info['name']}, broadcast=True)
        emit('user_list', list(connected_users.values()), broadcast=True)

@socketio.on('join')
def handle_join(data):
    username = data.get('username', 'Anonymous')
    connected_users[request.sid] = {
        'id': request.sid,
        'name': username,
        'joined': datetime.now().isoformat()
    }
    emit('user_joined', connected_users[request.sid], broadcast=True)
    emit('user_list', list(connected_users.values()), broadcast=True)

@socketio.on('message')
def handle_message(data):
    sender = connected_users.get(request.sid, {'name': 'Anonymous'})
    message_data = {
        'sender': sender['name'],
        'text': data['text'],
        'timestamp': datetime.now().isoformat(),
        'senderId': request.sid
    }
    emit('message', message_data, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)