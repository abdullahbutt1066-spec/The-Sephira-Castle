import os
from flask import Flask, render_template, request, redirect, url_for, session, make_response
import auth
import messages as msg_store
from db import init_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-fallback-key")
init_db()


@app.context_processor
def inject_nav_unread():
    user = session.get("user")
    if user:
        try:
            return {"nav_unread": msg_store.total_unread_for(user)}
        except Exception:
            return {"nav_unread": 0}
    return {"nav_unread": 0}


def current_user():
    return session.get("user")


def client_ip():
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    message = None
    success = False

    if request.method == "POST":
        codename = request.form.get("codename", "").strip()
        gender   = request.form.get("gender", "").strip().lower()
        password = request.form.get("password", "").strip()
        recovery = request.form.get("recovery_password", "").strip()

        members = auth.load_members()
        is_fool_registration = (codename == "The Fool")
        ip = client_ip()

        if not codename or not password:
            message = "Codename and password are required."
        elif codename not in auth.CARDS:
            message = "Please choose one of the Major Arcana."
        elif auth.is_expelled(codename):
            message = "That name has been struck from the record."
        elif codename in members:
            message = "That codename is already taken."
        elif gender not in ("male", "female"):
            message = "Please choose a gender."
        elif is_fool_registration and not recovery:
            message = "The Fool must set a recovery password."
        elif is_fool_registration and recovery == password:
            message = "Recovery password must be different from your login password."
        elif not is_fool_registration and auth.count_registrations_from_ip(ip) >= auth.IP_LIMIT:
            message = "Don't try to impersonate someone else. Or else your consequences will be dire."
        else:
            salt = auth.make_salt()
            symbol, color = auth.get_card_decorations(codename)
            entry = {
                "salt": salt,
                "password": auth.hash_password(password, salt),
                "gender": gender,
                "is_fool": is_fool_registration,
                "recovery_hash": None,
                "device_tokens": [],
                "ip": ip,
                "symbol": symbol,
                "color": color,
            }
            if is_fool_registration:
                rec_salt = auth.make_salt()
                entry["recovery_hash"] = auth.hash_password(recovery, rec_salt) + ":" + rec_salt
            members[codename] = entry
            auth.save_members(members)
            message = f"Welcome to the club, {auth.title_for(gender)} {auth.display_name(codename)}."
            success = True

    all_members = auth.load_members()
    taken = list(all_members.keys())

    return render_template(
        "register.html",
        message=message,
        success=success,
        cards=auth.CARDS,
        taken=taken,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    message = None

    if request.method == "POST":
        codename = request.form.get("codename", "").strip()
        password = request.form.get("password", "").strip()

        if auth.is_expelled(codename):
            message = "You have been expelled from the club."
        else:
            members = auth.load_members()
            if codename in members:
                info = members[codename]
                if info["password"] == auth.hash_password(password, info["salt"]):
                    if info.get("is_fool"):
                        token = request.cookies.get("fool_device")
                        if token and token in info.get("device_tokens", []):
                            session["user"] = codename
                            return redirect(url_for("members"))
                        else:
                            session["pending_fool_login"] = codename
                            return redirect(url_for("fool_bind"))
                    else:
                        session["user"] = codename
                        return redirect(url_for("members"))

            message = "You are not worthy, nor are you the chosen one."

    return render_template("login.html", message=message)


@app.route("/fool-bind", methods=["GET", "POST"])
def fool_bind():
    pending = session.get("pending_fool_login")
    if pending != "The Fool":
        return redirect(url_for("login"))

    message = None

    if request.method == "POST":
        recovery = request.form.get("recovery_password", "").strip()
        members = auth.load_members()
        info = members.get("The Fool")

        if not info:
            return redirect(url_for("login"))

        if not auth.verify_recovery(recovery, info.get("recovery_hash")):
            message = "The recovery password is incorrect."
        elif len(info.get("device_tokens", [])) >= auth.DEVICE_LIMIT:
            message = "Two devices are already bound. Release one before binding another."
        else:
            new_token = auth.make_device_token()
            info.setdefault("device_tokens", []).append(new_token)
            auth.save_members(members)
            session.pop("pending_fool_login", None)
            session["user"] = "The Fool"
            resp = make_response(redirect(url_for("members")))
            resp.set_cookie("fool_device", new_token, max_age=60*60*24*365, httponly=True, samesite="Lax")
            return resp

    return render_template("fool_bind.html", message=message)


@app.route("/members")
def members():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    all_members = auth.load_members()
    if user not in all_members:
        session.pop("user", None)
        return redirect(url_for("login"))

    info = all_members[user]
    title = auth.title_for(info["gender"])
    display = auth.display_name(user)

    listing = []
    for name, m in all_members.items():
        listing.append({
            "title": auth.title_for(m["gender"]),
            "display": auth.display_name(name),
            "symbol": m.get("symbol") or "·",
            "color": m.get("color") or "#b8b0c8",
            "is_fool": m.get("is_fool", False),
        })

    return render_template(
        "members.html",
        title=title,
        display=display,
        members=listing,
        is_fool=info.get("is_fool", False),
    )


@app.route("/chat", methods=["GET", "POST"])
def chat():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    all_members = auth.load_members()
    if user not in all_members:
        session.pop("user", None)
        return redirect(url_for("login"))

    info = all_members[user]
    is_fool = info.get("is_fool", False)

    if request.method == "POST":
        text = request.form.get("text", "").strip()
        if text:
            msg_store.add_message(user, text)
        return redirect(url_for("chat"))

    title = auth.title_for(info["gender"])
    display = auth.display_name(user)

    raw = msg_store.load_messages(include_deleted=is_fool)
    decorated = []
    for m in raw:
        sender = m.get("from", "")
        sender_info = all_members.get(sender)
        if sender_info:
            sender_title = auth.title_for(sender_info["gender"])
            sender_display = auth.display_name(sender)
            sender_symbol = sender_info.get("symbol") or "·"
            sender_color = sender_info.get("color") or "#b8b0c8"
        else:
            sender_title = ""
            sender_display = sender
            sender_symbol = "·"
            sender_color = "#b8b0c8"

        decorated.append({
            "id": m.get("id"),
            "sender_title": sender_title,
            "sender_display": sender_display,
            "sender_symbol": sender_symbol,
            "sender_color": sender_color,
            "text": m.get("text", ""),
            "time": m.get("time", ""),
            "deleted": m.get("deleted", False),
            "deleted_by": m.get("deleted_by", ""),
            "deleted_at": m.get("deleted_at", ""),
        })

    return render_template(
        "chat.html",
        title=title,
        display=display,
        messages=decorated,
        is_fool=is_fool,
    )


@app.route("/chat/delete", methods=["POST"])
def chat_delete():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    members = auth.load_members()
    if user not in members or not members[user].get("is_fool"):
        return redirect(url_for("chat"))

    message_id = request.form.get("message_id", "").strip()
    if message_id.isdigit():
        msg_store.soft_delete_message(int(message_id), deleted_by="The Fool")

    return redirect(url_for("chat"))


@app.route("/admin")
def admin():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    members = auth.load_members()
    if user not in members or not members[user].get("is_fool"):
        return redirect(url_for("members"))

    listing = []
    for name, info in members.items():
        listing.append({
            "codename": name,
            "title": auth.title_for(info["gender"]),
            "display": auth.display_name(name),
            "is_fool": info.get("is_fool", False),
        })

    expulsions = auth.load_expulsions()

    return render_template(
        "admin.html",
        members=listing,
        expulsions=expulsions,
        message=request.args.get("msg"),
        is_fool=True,
    )


@app.route("/admin/remove", methods=["POST"])
def admin_remove():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    members = auth.load_members()
    if user not in members or not members[user].get("is_fool"):
        return redirect(url_for("members"))

    target = request.form.get("codename", "").strip()

    if not target:
        return redirect(url_for("admin", msg="No target provided."))
    if target == "The Fool":
        return redirect(url_for("admin", msg="You cannot remove yourself."))
    if target not in members:
        return redirect(url_for("admin", msg="That member does not exist."))

    msg_store.tombstone_messages_from(target)
    auth.record_expulsion(target, expelled_by="The Fool")
    auth.remove_member(target)

    return redirect(url_for("admin", msg=f"{target} has been expelled."))


@app.route("/messages")
def messages_list():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    members = auth.load_members()
    if user not in members:
        session.pop("user", None)
        return redirect(url_for("login"))

    info = members[user]
    is_fool = info.get("is_fool", False)

    threads = msg_store.load_threads_for(user)

    return render_template(
        "messages.html",
        title=auth.title_for(info["gender"]),
        display=auth.display_name(user),
        is_fool=is_fool,
        threads=threads,
    )


@app.route("/messages/<int:thread_id>")
def messages_thread(thread_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    members = auth.load_members()
    if user not in members:
        session.pop("user", None)
        return redirect(url_for("login"))

    if not msg_store.is_member_of_thread(thread_id, user):
        return redirect(url_for("messages_list"))

    info = members[user]
    is_fool = info.get("is_fool", False)

    thread = msg_store.load_thread(thread_id)
    if not thread:
        return redirect(url_for("messages_list"))

    others = [p for p in thread["participants"] if p != user]
    if len(others) == 1:
        thread_title = others[0]
    elif others:
        thread_title = ", ".join(others)
    else:
        thread_title = "(empty)"

    participants_str = ", ".join(thread["participants"])

    raw = msg_store.load_dm_messages(thread_id, include_deleted=is_fool)

    decorated = []
    newest_id = 0
    for m in raw:
        sender = m.get("from", "")
        s_info = members.get(sender)
        if s_info:
            s_title = auth.title_for(s_info["gender"])
            s_display = auth.display_name(sender)
            s_symbol = s_info.get("symbol") or "·"
            s_color = s_info.get("color") or "#b8b0c8"
        else:
            s_title = ""
            s_display = sender
            s_symbol = "·"
            s_color = "#b8b0c8"

        decorated.append({
            "id": m.get("id"),
            "sender_title": s_title,
            "sender_display": s_display,
            "sender_symbol": s_symbol,
            "sender_color": s_color,
            "text": m.get("text", ""),
            "time": m.get("time", ""),
            "deleted": m.get("deleted", False),
            "deleted_by": m.get("deleted_by", ""),
            "deleted_at": m.get("deleted_at", ""),
        })
        if m.get("id") and m["id"] > newest_id:
            newest_id = m["id"]

    msg_store.mark_thread_read(thread_id, user, newest_id)

    return render_template(
        "messages_thread.html",
        title=auth.title_for(info["gender"]),
        display=auth.display_name(user),
        is_fool=is_fool,
        thread_id=thread_id,
        thread_title=thread_title,
        participants_str=participants_str,
        messages=decorated,
    )


@app.route("/messages/<int:thread_id>/send", methods=["POST"])
def messages_thread_send(thread_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    if not msg_store.is_member_of_thread(thread_id, user):
        return redirect(url_for("messages_list"))

    text = request.form.get("text", "").strip()
    if text:
        msg_store.add_dm_message(thread_id, user, text)

    return redirect(url_for("messages_thread", thread_id=thread_id))


@app.route("/messages/<int:thread_id>/delete", methods=["POST"])
def messages_thread_delete(thread_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    members = auth.load_members()
    if user not in members or not members[user].get("is_fool"):
        return redirect(url_for("messages_list"))

    message_id = request.form.get("message_id", "").strip()
    if message_id.isdigit():
        msg_store.soft_delete_dm_message(int(message_id), deleted_by="The Fool")

    return redirect(url_for("messages_thread", thread_id=thread_id))


@app.route("/messages/new", methods=["GET", "POST"])
def messages_new():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    members = auth.load_members()
    if user not in members or not members[user].get("is_fool"):
        return redirect(url_for("messages_list"))

    if request.method == "POST":
        selected = request.form.getlist("members")
        selected = [s for s in selected if s in members]
        if selected:
            thread_id = msg_store.create_thread(selected)
            return redirect(url_for("messages_thread", thread_id=thread_id))

    candidates = []
    for name, info in members.items():
        if info.get("is_fool"):
            continue
        candidates.append({
            "codename": name,
            "title": auth.title_for(info["gender"]),
            "display": auth.display_name(name),
        })

    return render_template(
        "messages_new.html",
        title=auth.title_for(members[user]["gender"]),
        display=auth.display_name(user),
        is_fool=True,
        candidates=candidates,
    )


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
