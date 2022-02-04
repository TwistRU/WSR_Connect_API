from datetime import datetime, timedelta

from flask import url_for
from flask_jwt_extended import create_access_token

from config import db


class TokenBlocklist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)


class Invitations(db.Model):
    __tablename__ = "invitations"
    invite_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.company_id"), nullable=False)
    company = db.relationship("Companies", backref=db.backref("invitations", lazy=True))
    recipient_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    recipient = db.relationship("Users", backref=db.backref("invitations", lazy=True))
    content = db.Column(db.String, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def get_info(self):
        img = None
        if self.company.img is not None:
            img = url_for("get_file", file_nick=self.company.img.file_nick)
        return {
            "invite_id": self.invite_id,
            "company_id": self.company_id,
            "company_name": self.company.title,
            "invite_body": self.content,
            "img_url": img
        }


class Users(db.Model):
    __tablename__ = 'users'
    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String, unique=True, index=True, nullable=False)
    first_name = db.Column(db.String, nullable=True)
    last_name = db.Column(db.String, nullable=True)
    password = db.Column(db.String, nullable=False)
    email = db.Column(db.String, unique=True, nullable=False)
    img_id = db.Column(db.Integer, db.ForeignKey('files.file_id'), nullable=True)
    img = db.relationship("Files", backref=db.backref('user', lazy=True))
    company_id = db.Column(db.Integer, nullable=True)
    company = db.relationship('Companies', backref=db.backref('users', lazy=True))
    about_me = db.Column(db.String, nullable=True)
    db.ForeignKeyConstraint(("company_id",), ("companies.company_id",))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def get_token(self, expire_time=24):
        expire_delta = timedelta(days=expire_time)
        token = create_access_token(identity=self.user_id, expires_delta=expire_delta)
        return token

    def get_info(self):
        img = None
        if self.img is not None:
            img = url_for("get_file", file_nick=self.img.file_nick)
        return {
            "user_id": self.user_id,
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "img_url": img,
            "company_id": self.company_id,
            "about_me": self.about_me
        }


class Files(db.Model):
    __tablename__ = "files"
    file_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    file_nick = db.Column(db.String, unique=True, nullable=False)
    filename = db.Column(db.String, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def get_info(self):
        return self.file_nick


class Companies(db.Model):
    __tablename__ = 'companies'
    company_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    img_id = db.Column(db.Integer, db.ForeignKey("files.file_id"))
    img = db.relationship(Files)
    title = db.Column(db.String, unique=True, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def get_info(self):
        img = None
        if self.img is not None:
            img = url_for("get_file", file_nick=self.img.file_nick)
        return {
            "company_id": self.company_id,
            "company_name": self.title,
            "img_url": img,
        }


class Chats(db.Model):
    __tablename__ = "chats"
    chat_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    chat_name = db.Column(db.String, nullable=False)
    img_id = db.Column(db.Integer, db.ForeignKey("files.file_id"), nullable=True)
    img = db.relationship(Files)
    creator_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    creator = db.relationship(Users)
    is_group = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class ChatParticipants(db.Model):
    __tablename__ = "chat_participants"
    chat_id = db.Column(db.Integer, db.ForeignKey("chats.chat_id", ondelete="CASCADE"), primary_key=True,
                        nullable=False)
    chat = db.relationship('Chats', backref=db.backref('participants', cascade="delete, delete-orphan", lazy=True))
    participant_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete="CASCADE"), primary_key=True,
                               nullable=False)
    participant = db.relationship('Users',
                                  backref=db.backref('chats', cascade="delete, delete-orphan", order_by=chat_id,
                                                     lazy=True))
    is_mute = db.Column(db.Boolean, nullable=False, default=False)
    is_pinned = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def get_info(self, found_message=None):
        last_message = found_message
        if found_message is None:
            last_messages = list(reversed(list(filter(lambda x: x.created_at, self.chat.messages))))
            if len(last_messages) > 0:
                last_message = last_messages[0].get_info()
            else:
                last_message = None
        img = None
        chat_name = "None"
        if not self.chat.is_group:
            for relation in self.chat.participants:
                if relation.participant != self.participant:
                    chat_name = relation.participant.first_name + " " + relation.participant.last_name
                    if relation.participant.img is not None:
                        img = url_for("get_file", file_nick=relation.participant.img.file_nick)
                    break
        else:
            chat_name = self.chat.chat_name
            if self.chat.img is not None:
                img = url_for("get_file", file_nick=self.chat.img.file_nick)
        return {
            "chat_name": chat_name,
            "chat_id": self.chat_id,
            "last_message": last_message,
            "mute": self.is_mute,
            "pin": self.is_pinned,
            "group": self.chat.is_group,
            "img_url": img,
        }


class Messages(db.Model):
    __tablename__ = "messages"
    message_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    creator_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    creator = db.relationship('Users', backref=db.backref('messages', lazy=True))
    chat_id = db.Column(db.Integer, db.ForeignKey("chats.chat_id"), nullable=False)
    chat = db.relationship('Chats', backref=db.backref('messages', lazy=True))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    message_body = db.Column(db.Text, nullable=True)
    parent_message_id = db.Column(db.Integer, nullable=True)
    img_id = db.Column(db.Integer, db.ForeignKey("files.file_id"), nullable=True)
    img = db.relationship(Files)
    read = db.Column(db.Boolean, default=False, nullable=False)
    was_edited = db.Column(db.Boolean, default=False, nullable=False)
    db.ForeignKeyConstraint(("parent_message_id",), ("messages.message_id",))

    def get_info(self):
        parent = self.query.filter_by(message_id=self.parent_message_id).first()
        if parent is not None:
            parent = parent.get_info()
        img = None
        creator_img = None
        if self.img is not None:
            img = url_for("get_file", file_nick=self.img.file_nick)
        if self.creator.img is not None:
            creator_img = url_for("get_file", file_nick=self.creator.img.file_nick)
        return {
            "message_id": self.message_id,
            "creator_id": self.creator_id,
            "creator_name": self.creator.username,
            "chat_id": self.chat_id,
            "created_at": self.created_at.strftime("%Y-%m-%d %X"),
            "message_body": self.message_body,
            "img_url": img,
            "creator_img_url": creator_img,
            "parent_message": parent,
            "read": self.read,
            "edit": self.was_edited,
        }


class Tables(db.Model):
    __tablename__ = "tables"
    table_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    creator = db.relationship("Users")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.company_id', ondelete="cascade"), nullable=False)
    company = db.relationship("Companies", backref=db.backref("tables", lazy=True))
    img_id = db.Column(db.Integer, db.ForeignKey('files.file_id'))
    img = db.relationship("Files")
    title = db.Column(db.String, nullable=False)

    def get_info(self):
        img = None
        if self.img is not None:
            img = url_for("get_file", file_nick=self.img.file_nick)
        return {
            "board_id": self.table_id,
            "board_creator_id": self.creator_id,
            "board_creator": self.creator.username,
            "board_name": self.title,
            "board_create_date": self.created_at.strftime("%Y-%m-%d %X"),
            "board_user_count": len(self.participants),
            "img_url": img
        }


class Columns(db.Model):
    __tablename__ = "columns"
    column_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String, nullable=False)
    table_id = db.Column(db.Integer, db.ForeignKey('tables.table_id', ondelete="cascade"), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    column_position = db.Column(db.Integer, nullable=False)
    creator = db.relationship("Users")
    table = db.relationship('Tables', backref=db.backref('columns', lazy=True, order_by=column_position,
                                                         cascade="delete"))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def get_info(self):
        return {
            "column_id": self.column_id,
            "board_id": self.table_id,
            "column_title": self.title,
            "column_position": self.column_position,
        }


class Cards(db.Model):
    __tablename__ = 'cards'
    card_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    creator = db.relationship(Users)
    column_id = db.Column(db.Integer, db.ForeignKey('columns.column_id', ondelete="cascade"), nullable=False)
    column = db.relationship('Columns', backref=db.backref('cards', lazy=True, cascade="delete"))
    table_id = db.Column(db.Integer, db.ForeignKey('tables.table_id', ondelete="cascade"), nullable=False)
    table = db.relationship('Tables', backref=db.backref('cards', lazy=True, cascade="delete"))
    title = db.Column(db.String, nullable=False)
    short_description = db.Column(db.String, nullable=True)
    long_description = db.Column(db.String, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    deadline = db.Column(db.DateTime, nullable=True)

    def get_info_with_users(self):
        users = list(map(lambda x: x.participant.get_info(), self.participants))
        return {**self.get_info(),
                "card_long_desc": self.long_description,
                "users": users
                }

    def get_info(self):
        deadline = None
        if self.deadline is not None:
            deadline = self.deadline.strftime("%Y-%m-%d %X")
        return {
            "card_id": self.card_id,
            "column_id": self.column_id,
            "board_id": self.table_id,
            "card_title": self.title,
            "card_creator_id": self.creator_id,
            "card_creator": self.creator.username,
            "card_short_desc": self.short_description,
            "create_date": self.created_at.strftime("%Y-%m-%d %X"),
            "deadline": deadline
        }


class CardParticipants(db.Model):
    __tablename__ = 'card_participants'
    card_id = db.Column(db.Integer, db.ForeignKey('cards.card_id', ondelete="cascade"), primary_key=True, nullable=False)
    card = db.relationship('Cards', backref=db.backref('participants', lazy=True, cascade="delete"))
    participant_id = db.Column(db.Integer(), db.ForeignKey('users.user_id', ondelete="CASCADE"), primary_key=True, nullable=False)
    participant = db.relationship('Users', backref=db.backref('cards', lazy=True, cascade="delete"))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class TableParticipants(db.Model):
    __tablename__ = 'table_participants'
    table_id = db.Column(db.Integer, db.ForeignKey('tables.table_id', ondelete="CASCADE"), primary_key=True,
                         nullable=False)
    participant_id = db.Column(db.Integer(), db.ForeignKey('users.user_id', ondelete="CASCADE"), primary_key=True,
                               nullable=False)
    table = db.relationship('Tables',
                            backref=db.backref('participants', order_by=participant_id, lazy=True, cascade="delete"))
    participant = db.relationship('Users', backref=db.backref('tables', lazy=True, cascade="delete"))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
