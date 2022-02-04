from flask_jwt_extended import decode_token
from flask_socketio import join_room

from config import socketio
from models import Users


@socketio.on('connect')
def connectEvent():
    print(f"Client connected")
    # emit()


@socketio.on("authorization")
def authorizationEvent(data):
    if data != "":
        print("Client authorization")
        user_id = decode_token(data)
        user = Users.query.filter_by(user_id=user_id['sub']).first()
        for chat in user.chats:
            join_room(f"chat_{chat.chat_id}")
    else:
        raise ConnectionRefusedError("unauthorized!")


@socketio.on('disconnect')
def test_disconnect():
    print('Client disconnected')
