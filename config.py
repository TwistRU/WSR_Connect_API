import os.path
from os import environ

from flask import Flask
from flask_hashing import Hashing
from flask_jwt_extended import JWTManager
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO

app = Flask(__name__)
# app.testing = True
# app.config["SERVER_NAME"] = "192.168.0.191:5000"
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.curdir, 'files')
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config["JWT_SECRET_KEY"] = "super-secret-key"
if environ.get("FLASK_ENV") != 'development':
    app.config['SQLALCHEMY_DATABASE_URI'] = environ.get('DATABASE_URL', '').replace('postgres', 'postgresql', 1)
else:
    app.debug = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://twistru:romashka.002@localhost:5432/WSR Connect Test'
db = SQLAlchemy(app)
jwt = JWTManager(app)
hashing = Hashing(app)
socketio = SocketIO(app)
# client.set_cookie(key="", server_name="localhost:80")
