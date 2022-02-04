from os import environ

from routes import *
from socketEvents import *

if __name__ == '__main__':
    # db.drop_all()
    db.create_all()
    port = int(environ.get("PORT", 5000))
    socketio.run(app=app, host='0.0.0.0', port=port)
