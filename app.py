import os
from flask import Flask, render_template, request, redirect, url_for, session, make_response
import auth
import messages as msg_store
from db import init_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-fallback-key")
init_db()


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
            entry = {
                "salt": salt,
                "password": auth.hash_password(password, salt),
                "gender": gender,
                "is_fool": is_fool_registration,
                "recovery_hash": None,
                "device_tokens": [],
                "ip": ip,
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
        listing.append(f"{auth.title_for(m['gender'])} {auth.display_name(name)}")

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
        else:
            sender_title = ""
            sender_display = sender

        decorated.append({
            "id": m.get("id"),
            "sender_title": sender_title,
            "sender_display": sender_display,
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


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
