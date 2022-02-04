import os
from collections import defaultdict
from time import timezone

from flask import request, jsonify, send_from_directory
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from flask_socketio import emit
from sqlalchemy import or_
from werkzeug.utils import secure_filename

from config import ALLOWED_EXTENSIONS, app, jwt, hashing
from models import *


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload):
    jti = jwt_payload["jti"]
    token = db.session.query(TokenBlocklist.id).filter_by(jti=jti).scalar()
    return token is not None


@app.route('/auth/login', methods=['POST'])
def login():  # put application's code here
    print(request.json)
    if request.json is not None:
        username = request.json.get("username", None)
        password = request.json.get("password", None)
        req = Users.query.filter_by(username=username, password=password).first()
        if req is None:
            return jsonify(success=False, errors=["Login or password incorrect"])
        return jsonify(success=True, token=req.get_token(), errors=[], my_id=req.user_id)
    return jsonify(success=False, errors=["Don't have json"])


@app.route("/auth/logout", methods=["DELETE"])
@jwt_required()
def logout():
    jti = get_jwt()["jti"]
    now = datetime.now(timezone.utc)
    db.session.add(TokenBlocklist(jti=jti, created_at=now))
    db.session.commit()
    return jsonify(msg="JWT revoked")


@app.route('/auth/registration', methods=['POST'])
def registration():
    errors = []
    if request.json is not None:
        username = request.json["username"]
        email = request.json["email"]
        password = request.json["password"]
        first_name = request.json["first_name"]
        last_name = request.json["last_name"]
        print(request.json)
        new = Users(username=username, email=email, password=password, first_name=first_name, last_name=last_name)
        db.session.add(new)
        db.session.commit()
        return jsonify(success=True, token=new.get_token(), errors=errors, my_id=new.user_id)
    else:
        errors.append("Don't have json")
    return jsonify(success=False, errors=errors)


@app.route('/profile/password', methods=['PUT'])
@jwt_required()
def set_user_password():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    if user.password == request.json['old_password']:
        user.password = request.json['new_password']
        db.session.commit()
        return jsonify(succes=True, errors=[])
    return jsonify(success=False, errors=["Incorrect password"])


@app.route('/profile/info', methods=['GET'])
@jwt_required()
def get_user_profile_info():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    return jsonify(user.get_info())


@app.route('/profile/info', methods=['PUT'])
@jwt_required()
def edit_user_profile_info():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    if "first_name" in request.json and request.json["first_name"] is not None:
        user.first_name = request.json["first_name"]
    if "last_name" in request.json and request.json["last_name"] is not None:
        user.last_name = request.json["last_name"]
    if "email" in request.json and request.json["email"] is not None:
        user.email = request.json["email"]
    if "about_me" in request.json and request.json["about_me"] is not None:
        user.about_me = request.json["about_me"]
    print(request.json)
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/auth/info', methods=['PUT'])
@jwt_required()
def set_auth_user_info():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    user.first_name = request.json["first_name"]
    user.last_name = request.json["last_name"]
    print(request.json)
    if "about_me" in request.json:
        user.about_me = request.json["about_me"]
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/chats', methods=['GET'])
@jwt_required()
def get_chats():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    search = request.args.get("search")
    chats = []
    if search is None:
        chats = list(
            map(lambda relation: {**relation.get_info(), "mine": (relation.chat.creator_id == user_id)},
                sorted(user.chats, key=lambda x: x.is_pinned, reverse=True)))
    elif search != "":
        messages = Messages.query.filter(Messages.message_body.like(f"%{search}%")).order_by(
            Messages.message_id.desc()).all()
        for message in messages:
            for relation in message.chat.participants:
                if relation.participant_id == message.creator_id:
                    chats.append(relation.get_info(message.get_info()))
                    chats[-1]["chat_name"] = message.creator.first_name + " " + message.creator.last_name
                    img = None
                    if message.creator.img is not None:
                        img = url_for("get_file", file_nick=message.creator.img.file_nick)
                    chats[-1]["img_url"] = img
                    chats[-1]["mine"] = relation.chat.creator_id == user_id
                    break
    return jsonify(success=True, chats=chats, errors=[])


@app.route('/chat/info', methods=['GET'])
@jwt_required()
def get_chat_info():
    user_id = get_jwt_identity()
    chat = Chats.query.filter_by(chat_id=request.args.get("chat_id")).first()
    if chat is None:
        return jsonify(success=False, errors=["Чат не существует"])
    users = list(map(lambda x: x.participant.get_info(), chat.participants))
    info = {"users": users}
    for relation in chat.participants:
        if relation.participant_id == user_id:
            info = {**relation.get_info(), **info, "mine": (chat.creator_id == user_id)}
            break
    return jsonify(info)


@app.route('/chat/new', methods=['GET'])
@jwt_required()
def create_chat():
    user_id = get_jwt_identity()
    Users.query.filter_by(user_id=user_id).first()
    another = request.args.get("user_id")
    chats = ChatParticipants.query.filter(or_(
        ChatParticipants.participant_id == user_id, ChatParticipants.participant_id == another))
    tmp_list = defaultdict(int)
    for relation in chats:
        tmp_list[relation.chat_id] += 1
        if tmp_list[relation.chat_id] == 2:
            return jsonify(relation.chat_id)
    chat = Chats(chat_name="None", creator_id=user_id)
    db.session.add(ChatParticipants(chat=chat, participant_id=user_id))
    db.session.add(ChatParticipants(chat=chat, participant_id=another))
    db.session.add(chat)
    db.session.commit()
    return jsonify(chat.chat_id)


@app.route('/chat/group', methods=['POST'])
@jwt_required()
def create_chat_group():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    chat_name = request.args.get("chat_name")
    chat = Chats(chat_name=chat_name, is_group=True, creator_id=user_id)
    if request.files.get("file", False):
        new_file_model = save_file(request.files["file"])
        chat.img = new_file_model
    db.session.add(ChatParticipants(chat=chat, participant_id=user_id))
    db.session.add(chat)
    db.session.commit()
    return jsonify(chat.chat_id)


@app.route('/chat/group', methods=['PUT'])
@jwt_required()
def edit_chat_group():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    chat_name = request.args.get("chat_name")
    chat_id = request.args.get("chat_id")
    chat = Chats.query.filter_by(chat_id=chat_id).first()
    if request.args.get("delete_img") is None:
        if request.files.get("file", False):
            new_file_model = save_file(request.files["file"])
            chat.img = new_file_model
    elif request.args.get("delete_img"):
        chat.img_id = None
    chat.chat_name = chat_name
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/company/users/quit', methods=['DELETE'])
@jwt_required()
def delete_company_user_quit():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    user.company_id = None
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/company/board/users/quit', methods=['DELETE'])
@jwt_required()
def delete_company_board_user_quit():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    board_id = request.args.get("board_id")
    db.session.delete(
        TableParticipants.query.filter_by(participant_id=user_id, table_id=board_id).first()
    )
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/company/board/column/card/users/quit', methods=['DELETE'])
@jwt_required()
def delete_company_board_column_card_user_quit():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    card_id = request.args.get("card_id")
    db.session.delete(
        CardParticipants.query.filter_by(participant_id=user_id, card_id=card_id).first()
    )
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/chat/group', methods=['DELETE'])
@jwt_required()
def delete_chat_group():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    chat_id = request.args.get("chat_id")
    chat = Chats.query.filter_by(chat_id=chat_id).first()
    if chat.creator_id != user_id:
        return jsonify(success=False, errors=["Вы не являетесь создателем чат-группы"])
    db.session.delete(chat)
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/users/search', methods=['GET'])
@jwt_required()
def get_users_to_chat():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    search = request.args.get("search")
    users = list(map(lambda x: x.get_info(), Users.query.filter_by(company_id=user.company_id).filter(
        (Users.first_name + Users.last_name).like(f"%{search}%"), Users.user_id != user_id).all()))
    return jsonify(success=True, errors=[], users=users)


@app.route('/profile/info/image', methods=['PUT'])
@jwt_required()
def set_user_avatar():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    file = request.files['file']
    new_file_model = save_file(file)
    user.img = new_file_model
    db.session.commit()
    return jsonify(success=True, url=url_for("get_file", file_nick=user.img.file_nick))


@app.route('/profile/info/image', methods=['DELETE'])
@jwt_required()
def delete_user_avatar():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    user.img_id = None
    db.session.commit()
    return jsonify(success=True, errors=[])


def save_file(file):
    filename = secure_filename(file.filename)
    new_file_model = Files(filename=filename, file_nick="")
    file_nick = hashing.hash_value(filename, salt=str(new_file_model.file_id))
    path = os.path.join(app.config['UPLOAD_FOLDER'], file_nick)
    file.save(path)
    new_file_model.file_nick = file_nick
    db.session.add(new_file_model)
    db.session.commit()
    return new_file_model


@app.route('/files/<file_nick>')
def get_file(file_nick):
    file = Files.query.filter_by(file_nick=file_nick).first()
    return send_from_directory(app.config["UPLOAD_FOLDER"], file_nick, download_name=file.filename)


@app.route('/company', methods=['POST'])
@jwt_required()
def create_company():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    company = Companies(creator_id=user_id, title=request.args.get("company_name"))
    db.session.add(company)
    db.session.commit()
    if request.files.get("file", False):
        new_file_model = save_file(request.files["file"])
        company.img = new_file_model
    print(company, company.company_id)
    user.company_id = company.company_id
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/company', methods=['PUT'])
@jwt_required()
def edit_company():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    company_name = request.args.get("company_name")
    company = Companies.query.filter_by(company_id=user.company_id).first()
    if request.args.get("delete_img") is None:
        if request.files.get("file", False):
            new_file_model = save_file(request.files["file"])
            company.img = new_file_model
    elif request.args.get("delete_img"):
        company.img_id = None
    company.title = company_name
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/company/board', methods=['PUT'])
@jwt_required()
def edit_company_board():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    title = request.args.get("board_name")
    table_id = request.args.get("board_id")
    table = Tables.query.filter_by(table_id=table_id).first()
    if request.args.get("delete_img") is None:
        if request.files.get("file", False):
            new_file_model = save_file(request.files["file"])
            table.img = new_file_model
    elif request.args.get("delete_img"):
        table.img_id = None
    table.title = title
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/company', methods=['GET'])
@jwt_required()
def get_company():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    company = Companies.query.filter_by(company_id=user.company_id).first()
    company_info = company.get_info()
    company_info["mine"] = company.creator_id == user_id
    return jsonify(company_info)


@app.route('/company/user', methods=['GET'])
@jwt_required()
def get_company_user():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    if user is None:
        return jsonify(success=False, errors=["Token is invalid. You need to login"])
    if user.company_id is None:
        return jsonify(success=False, errors=["You are not in company"])
    requested_user = Users.query.filter_by(user_id=request.args.get("user_id")).first()
    if requested_user is None:
        return jsonify(success=False, errors=["Requested user not found"])
    if user.company_id != requested_user.company_id:
        return jsonify(success=False, errors=["Not allowed"])
    return jsonify(requested_user.get_info())


@app.route('/company/board', methods=['POST'])
@jwt_required()
def create_company_board():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    table = Tables(creator_id=user_id, company_id=user.company_id, title=request.args.get("board_name"))
    if "file" in request.files:
        new_file_model = save_file(request.files["file"])
        table.img = new_file_model
    db.session.add(table)
    db.session.commit()
    db.session.add(TableParticipants(table_id=table.table_id, participant_id=user.user_id))
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/company/board/users', methods=['POST'])
@jwt_required()
def create_company_board_users():
    errors = []
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    table_id = request.args.get("board_id")
    table_users = list(
        map(lambda x: x.participant.get_info().get("user_id"),
            Tables.query.filter_by(table_id=table_id).first().participants))
    users_id = request.json.get("users")
    for i in users_id:
        if i not in table_users:
            db.session.add(TableParticipants(table_id=table_id, participant_id=i))
        else:
            errors.append(f"user with id - {i} already exists")
    db.session.commit()
    return jsonify(success=True, errors=errors)


@app.route('/company/board', methods=['GET'])
@jwt_required()
def get_company_boards():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    tables_info = []
    tables = Tables.query.filter_by(company_id=user.company_id).order_by(Tables.table_id)
    for table in tables:
        table_info = table.get_info()
        table_info["available"] = user in map(lambda x: x.participant, table.participants)
        table_info["mine"] = user_id == table.creator_id
        tables_info.append(table_info)
    return jsonify(success=True, errors=[], boards=tables_info)


@app.route('/company/board', methods=['DELETE'])
@jwt_required()
def delete_company_board():
    user_id = get_jwt_identity()
    Users.query.filter_by(user_id=user_id).first()
    table = Tables.query.filter_by(table_id=request.args.get("board_id")).first()
    db.session.delete(table)
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/company/users', methods=['GET'])
@jwt_required()
def get_company_users():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    search = request.args.get("search")
    if search is None or search == "":
        users = list(
            map(lambda x: x.get_info(),
                Users.query.filter_by(company_id=user.company_id).order_by(Users.user_id).all()))
    else:
        users = list(map(lambda x: x.get_info(), Users.query.filter_by(company_id=user.company_id).filter(
            (Users.first_name + Users.last_name).like(f"%{search}%"), Users.user_id != user_id).order_by(
            Users.user_id).all()))
    return jsonify(success=True, errors=[], users=users)


@app.route('/company/board/users', methods=['GET'])
@jwt_required()
def get_company_board_users():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    search = request.args.get("search")
    board_id = request.args.get("board_id")
    users = TableParticipants.query.filter_by(table_id=board_id)
    if search is None or search == "":
        users = list(map(lambda x: x.participant.get_info(), users.order_by(TableParticipants.participant_id).all()))
    else:
        users_1 = list(map(lambda x: x.participant, users.order_by(TableParticipants.participant_id).all()))
        users = []
        for user in users_1:
            if search.lower() in user.first_name.lower() + user.last_name.lower():
                users.append(user.get_info())
    return jsonify(success=True, errors=[], users=users)


@app.route('/users', methods=['GET'])
@jwt_required()
def get_users():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    search = request.args.get("search")
    if search is None or search == "":
        users = list(
            map(lambda x: x.get_info(),
                Users.query.filter_by(company_id=None).order_by(Users.user_id).all()))
    else:
        users = list(map(lambda x: x.get_info(), Users.query.filter_by(company_id=None).filter(
            Users.username.like(f"%{search}%"), Users.user_id != user_id).order_by(
            Users.user_id).all()))
    return jsonify(success=True, errors=[], users=users)


@app.route('/company/board/users', methods=['DELETE'])
@jwt_required()
def delete_company_board_user():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    db.session.delete(
        TableParticipants.query.filter_by(table_id=request.args.get("board_id"),
                                          participant_id=request.args.get("user_id")).first())
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/company/users', methods=['DELETE'])
@jwt_required()
def delete_company_users():
    Users.query.filter_by(user_id=request.args.get("user_id")).first().company_id = None
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/company/users/invite', methods=['POST'])
@jwt_required()
def create_company_user_invite():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    recipient_id = request.json["user_id"]
    tmp = Invitations.query.filter_by(recipient_id=recipient_id, company_id=user.company_id).first()
    if tmp is None:
        inv = Invitations(company_id=user.company_id, recipient_id=recipient_id, content=request.json["invite_text"])
        db.session.add(inv)
    else:
        tmp.content = request.json["invite_text"]
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/company/board/column', methods=['POST'])
@jwt_required()
def create_company_board_column():
    user_id = get_jwt_identity()
    table = Tables.query.filter_by(table_id=request.json["board_id"]).first()
    n = len(table.columns)
    col = Columns(creator_id=user_id, title=request.json["column_name"], table_id=table.table_id, column_position=n + 1)
    table.columns.append(col)
    db.session.add(col)
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/company/board/column', methods=['GET'])
@jwt_required()
def get_company_board_column():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    table = Tables.query.filter_by(table_id=request.args.get("board_id")).first()
    columns = table.columns
    answer = []
    for column in columns:
        column_info = column.get_info()
        column_info["mine"] = column.creator_id == user_id
        column_info["cards"] = []
        for card in column.cards:
            card_info = card.get_info()
            card_info["mine"] = user_id == card.creator_id
            relation = CardParticipants.query.filter_by(card=card, participant=user).first()
            card_info["available"] = relation is not None
            column_info["cards"].append(card_info)
        answer.append(column_info)
    return jsonify(success=True, errors=[], columns=answer)


@app.route('/company/board/column/card/detail', methods=['GET'])
@jwt_required()
def get_company_board_column_card_detail():
    card = Cards.query.filter_by(card_id=request.args.get("card_id")).first()
    if card is None:
        return jsonify(success=False, errors=["Карточка не найдена"])
    return jsonify(card.get_info_with_users())


@app.route('/company/board/column', methods=['PUT'])
@jwt_required()
def edit_company_board_column():
    col = Columns.query.filter_by(column_id=request.json["column_id"]).first()
    col.title = request.json["column_title"]
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/company/board/column', methods=['DELETE'])
@jwt_required()
def delete_company_board_column():
    col = Columns.query.filter_by(column_id=request.args.get("column_id")).first()
    db.session.delete(col)
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/company/board/column/card', methods=['POST'])
@jwt_required()
def create_company_board_column_card():
    user_id = get_jwt_identity()
    deadline = request.json.get("deadline")
    if deadline is not None:
        deadline = datetime.strptime(deadline, "%Y-%m-%d %X")
    card = Cards(creator_id=user_id, column_id=request.json["column_id"], table_id=request.json["board_id"],
                 title=request.json["card_title"], short_description=request.json["card_short_desc"],
                 long_description=request.json["card_long_desc"],
                 deadline=deadline)
    db.session.add(card)
    db.session.add(CardParticipants(card=card, participant_id=user_id))
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/company/board/column/card/users', methods=['POST'])
@jwt_required()
def create_company_board_column_card_users():
    errors = []
    user_id = get_jwt_identity()
    card_id = request.args.get("card_id")
    card_users = list(
        map(lambda x: x.participant.get_info().get("user_id"),
            Cards.query.filter_by(card_id=card_id).first().participants))
    users_id = request.json.get("users")
    for i in users_id:
        if i not in card_users:
            db.session.add(CardParticipants(card_id=card_id, participant_id=i))
        else:
            errors.append(f"user with id - {i} already exists")
    db.session.commit()
    return jsonify(success=True, errors=errors)


@app.route('/company/board/column/card/users', methods=['DELETE'])
@jwt_required()
def delete_company_board_column_card_user():
    user_id = get_jwt_identity()
    card_id = request.args.get("card_id")
    another_user_id = request.args.get("user_id")
    new_participant_model = CardParticipants.query.filter_by(card_id=card_id, participant_id=another_user_id).first()
    db.session.delete(new_participant_model)
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/company/board/column/card', methods=['PUT'])
@jwt_required()
def edit_company_board_column_card():
    card = Cards.query.filter_by(card_id=request.json["card_id"]).first()
    deadline = request.json.get("deadline")
    if deadline is not None:
        deadline = datetime.strptime(deadline, "%Y-%m-%d %X")
    card.title = request.json.get("card_title")
    card.deadline = deadline
    card.short_description = request.json.get("card_short_desc")
    card.long_description = request.json.get("card_long_desc")
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/company/board/column/card', methods=['DELETE'])
@jwt_required()
def delete_company_board_column_card():
    card = Cards.query.filter_by(card_id=request.args.get("card_id")).first()
    db.session.delete(card)
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/invitations', methods=['GET'])
@jwt_required()
def get_invitations():
    user_id = get_jwt_identity()
    Users.query.filter_by(user_id=user_id).first()
    inv = list(map(lambda x: x.get_info(), Invitations.query.filter_by(recipient_id=user_id).all()))
    return jsonify(success=True, errors=[], invitations=inv)


@app.route('/invitations', methods=['PUT'])
@jwt_required()
def accept_invitation():
    user_id = get_jwt_identity()
    user = Users.query.filter_by(user_id=user_id).first()
    inv = Invitations.query.filter_by(invite_id=request.json["invite_id"]).first()
    user.company_id = inv.company_id
    db.session.delete(inv)
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/chat/message', methods=['POST'])
@jwt_required()
def create_chat_message():
    user_id = get_jwt_identity()
    Users.query.filter_by(user_id=user_id).first()
    msg = Messages(
        creator_id=user_id,
        chat_id=request.json["chat_id"],
        message_body=request.json["message_body"],
        parent_message_id=request.json.get("replied_message_id", None)
    )
    db.session.add(msg)
    db.session.commit()
    emit("msg", msg.get_info(), to=f"chat_{msg.chat_id}", namespace='/')
    return jsonify(success=True, errors=[])


@app.route('/chat/message/image', methods=['POST'])
@jwt_required()
def create_chat_message_image():
    user_id = get_jwt_identity()
    Users.query.filter_by(user_id=user_id).first()
    msg = Messages(creator_id=user_id, chat_id=request.args.get("chat_id"))
    if "file" in request.files:
        new_file_model = save_file(request.files["file"])
        msg.img = new_file_model
    db.session.add(msg)
    db.session.commit()
    emit("msg", msg.get_info(), to=f"chat_{msg.chat_id}", namespace='/')
    return jsonify(success=True, errors=[])


@app.route('/chat/messages', methods=['GET'])
@jwt_required()
def get_chat_messages():
    user_id = get_jwt_identity()
    Users.query.filter_by(user_id=user_id).first()
    messages = Messages.query.filter_by(chat_id=request.args.get("chat_id")).order_by(Messages.message_id).all()
    ans = []
    for msg in messages:
        m = msg.get_info()
        m["mine"] = msg.creator_id == user_id
        ans.append(m)
    return jsonify(success=True, errors=[], messages=ans)


@app.route('/chat/message', methods=['PUT'])
@jwt_required()
def edit_chat_message():
    user_id = get_jwt_identity()
    Users.query.filter_by(user_id=user_id).first()
    message = Messages.query.filter_by(message_id=request.json.get("message_id")).first()
    message.message_body = request.json.get("message_body")
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/chat/message', methods=['DELETE'])
@jwt_required()
def delete_chat_message():
    user_id = get_jwt_identity()
    Users.query.filter_by(user_id=user_id).first()
    message = Messages.query.filter_by(message_id=request.args.get("message_id")).first()
    db.session.delete(message)
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/chat/pin', methods=['PUT'])
@jwt_required()
def set_chat_pin():
    user_id = get_jwt_identity()
    Users.query.filter_by(user_id=user_id).first()
    chat = ChatParticipants.query.filter_by(chat_id=request.json.get("chat_id"), participant_id=user_id).first()
    chat.is_pinned = request.json.get("status")
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/chat/mute', methods=['PUT'])
@jwt_required()
def set_chat_mute():
    user_id = get_jwt_identity()
    Users.query.filter_by(user_id=user_id).first()
    chat = ChatParticipants.query.filter_by(chat_id=request.json.get("chat_id"), participant_id=user_id).first()
    chat.is_mute = request.json.get("status")
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/chat/quit', methods=['DELETE'])
@jwt_required()
def delete_chat_user():
    user_id = get_jwt_identity()
    Users.query.filter_by(user_id=user_id).first()
    chat = ChatParticipants.query.filter_by(chat_id=request.args.get("chat_id"), participant_id=user_id).first()
    db.session.delete(chat)
    db.session.commit()
    return jsonify(success=True, errors=[])


@app.route('/chat/group/users', methods=['POST'])
@jwt_required()
def create_chat_group_users():
    errors = []
    user_id = get_jwt_identity()
    chat_id = request.args.get("chat_id")
    chat_users = list(
        map(lambda x: x.participant.get_info().get("user_id"),
            Chats.query.filter_by(chat_id=chat_id).first().participants))
    users_id = request.json.get("users")
    for i in users_id:
        if i not in chat_users:
            db.session.add(ChatParticipants(chat_id=chat_id, participant_id=i))
        else:
            errors.append(f"user with id - {i} already exists")
    db.session.commit()
    return jsonify(success=True, errors=errors)


@app.route('/chat/group/users', methods=['DELETE'])
@jwt_required()
def delete_chat_group_user():
    user_id = get_jwt_identity()
    Users.query.filter_by(user_id=user_id).first()
    chat_id = request.args.get("chat_id")
    another_user_id = request.args.get("user_id")
    chat = Chats.query.filter_by(chat_id=chat_id).first()
    if chat.creator_id != user_id:
        return jsonify(success=False, errors=["Вы не являетесь создателем чат-группы"])
    relation_model = ChatParticipants.query.filter_by(chat_id=chat_id, participant_id=another_user_id).first()
    db.session.delete(relation_model)
    db.session.commit()
    return jsonify(success=True, errors=[])
