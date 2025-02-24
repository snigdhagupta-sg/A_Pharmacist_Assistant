from flask import Flask, request
from flask_socketio import SocketIO, emit, disconnect, join_room, leave_room
from flask_cors import CORS
from datetime import datetime
import hashlib
import logging
from termcolor import colored
from typing import Dict, Any, Optional
import secrets

# Custom logger setup
class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': 'grey',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'red',
    }

    def format(self, record):
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = colored(levelname, self.COLORS[levelname], attrs=['bold'])
        
        record.timestamp = colored(
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'blue'
        )
        
        if hasattr(record, 'msg'):
            if 'connected' in str(record.msg).lower():
                record.msg = colored(record.msg, 'green')
            elif 'disconnected' in str(record.msg).lower():
                record.msg = colored(record.msg, 'yellow')
            elif 'error' in str(record.msg).lower():
                record.msg = colored(record.msg, 'red')
            elif 'joined' in str(record.msg).lower():
                record.msg = colored(record.msg, 'cyan')
            elif 'message' in str(record.msg).lower():
                record.msg = colored(record.msg, 'magenta')
        
        return super().format(record)

logger = logging.getLogger('ChatServer')
logger.setLevel(logging.DEBUG)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = ColoredFormatter('%(timestamp)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
CORS(app, resources={r"/*": {"origins": "*"}})

socketio = SocketIO(app, 
    cors_allowed_origins="*",
    async_mode='gevent',
    ping_timeout=60,
    ping_interval=25,
    logger=True,
    engineio_logger=True
)

class User:
    def __init__(self, sid: str, username: Optional[str] = None):
        self.sid = sid
        self.username = username or f"Guest_{secrets.token_hex(4)}"
        self.room: Optional[str] = None
        self.connected_at = datetime.now()
        self.last_active = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.sid,
            'username': self.username,
            'room': self.room
        }

class Room:
    def __init__(self, name: str, password: Optional[str] = None):
        self.name = name
        self.password = password
        self.members: Dict[str, User] = {}
        self.created_at = datetime.now()

    def verify_password(self, password: Optional[str]) -> bool:
        if not self.password:
            return True
        return self.password == hashlib.sha256(password.encode()).hexdigest() if password else False

    def add_member(self, user: User) -> None:
        self.members[user.sid] = user
        user.room = self.name

    def remove_member(self, user_sid: str) -> Optional[User]:
        user = self.members.pop(user_sid, None)
        if user:
            user.room = None
        return user

rooms: Dict[str, Room] = {}
users: Dict[str, User] = {}

@socketio.on('connect')
def handle_connect():
    sid = request.sid
    # Create a new user with temporary guest name
    new_user = User(sid)
    users[sid] = new_user
    logger.info(f'📥 Client connected: {sid} (Temporary username: {new_user.username})')
    # Notify the client of their temporary username
    emit('user_connected', {
        'id': sid,
        'username': new_user.username
    })

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    user = users.get(sid)
    if user:
        if user.room:
            room = rooms.get(user.room)
            if room:
                room.remove_member(sid)
                emit('user_left', user.to_dict(), room=user.room)
                update_user_list(user.room)
                logger.info(f'👋 User {user.username} left room {user.room}')
        logger.info(f'📤 Client disconnected: {user.username} ({sid})')
        del users[sid]

@socketio.on('create_room')
def handle_create_room(data: Dict[str, str]):
    room_name = data['room']
    password = data.get('password')
    username = data['username']
    
    # Update user's username
    user = users.get(request.sid)
    if user:
        user.username = username
    
    if room_name in rooms:
        logger.error(f'❌ Failed to create room {room_name}: Room already exists')
        emit('error', {'message': 'Room already exists'})
        return
    
    hashed_password = hashlib.sha256(password.encode()).hexdigest() if password else None
    rooms[room_name] = Room(room_name, hashed_password)
    logger.info(f'🏗️  Room created: {room_name} by {username}')
    emit('room_created', {'room': room_name})
    handle_join_room(data)

@socketio.on('join_room')
def handle_join_room(data: Dict[str, str]):
    room_name = data['room']
    password = data.get('password')
    username = data['username']
    
    # Update user's username
    user = users.get(request.sid)
    if user:
        user.username = username
    else:
        user = User(request.sid, username)
        users[request.sid] = user
    
    room = rooms.get(room_name)
    if not room:
        logger.error(f'❌ Failed to join room {room_name}: Room does not exist')
        emit('error', {'message': 'Room does not exist'})
        return
    
    if not room.verify_password(password):
        logger.error(f'❌ Failed to join room {room_name}: Invalid password')
        emit('error', {'message': 'Invalid password'})
        return
    
    join_room(room_name)
    room.add_member(user)
    
    logger.info(f'✨ User {username} joined room {room_name}')
    emit('room_joined', {'room': room_name, 'username': username})
    update_user_list(room_name)

def update_user_list(room_name: str):
    room = rooms.get(room_name)
    if room:
        user_list = [user.to_dict() for user in room.members.values()]
        emit('user_list', {'users': user_list}, room=room_name)
        logger.debug(f'📊 Updated user list for room {room_name}: {len(user_list)} users')

@socketio.on('message')
def handle_message(data: Dict[str, str]):
    user = users.get(request.sid)
    
    if not user or not user.room:
        logger.error(f'❌ Message failed: User not in any room')
        emit('error', {'message': 'You must join a room before sending messages'})
        return
    
    if 'text' not in data or not data['text'].strip():
        logger.error(f'❌ Message failed: Empty message')
        emit('error', {'message': 'Cannot send empty message'})
        return

    message_data = {
        'sender': user.username,
        'text': data['text'].strip(),
        'timestamp': datetime.now().isoformat(),
        'room': user.room
    }
    logger.info(f'💬 Message from {user.username} in {user.room}: {data["text"][:50]}...')
    emit('message', message_data, room=user.room)

if __name__ == '__main__':
    logger.info('🚀 Starting chat server...')
    socketio.run(app, 
        debug=True, 
        host='0.0.0.0', 
        port=5000,
        allow_unsafe_werkzeug=True,
        use_reloader=False
    )