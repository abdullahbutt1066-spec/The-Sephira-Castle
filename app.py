import os
from flask import Flask, render_template, request, redirect, url_for, session
import auth
import messages as msg_store
from db import init_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-fallback-key")
init_db()


def current_user():
    """Return the logged-in codename, or None."""
    return session.get("user")


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

        members = auth.load_members()

        if not codename or not password:
            message = "Codename and password are required."
        elif codename in members:
            message = "That codename is already taken."
        elif gender not in ("male", "female"):
            message = "Please choose a gender."
        else:
            salt = auth.make_salt()
            members[codename] = {
                "salt": salt,
                "password": auth.hash_password(password, salt),
                "gender": gender,
            }
            auth.save_members(members)
            message = f"Welcome to the club, {auth.title_for(gender)} {auth.display_name(codename)}."
            success = True

    return render_template("register.html", message=message, success=success)


@app.route("/login", methods=["GET", "POST"])
def login():
    message = None

    if request.method == "POST":
        codename = request.form.get("codename", "").strip()
        password = request.form.get("password", "").strip()
        members = auth.load_members()

        if codename in members:
            info = members[codename]
            if info["password"] == auth.hash_password(password, info["salt"]):
                session["user"] = codename
                return redirect(url_for("members"))

        message = "You are not worthy, nor are you the chosen one."

    return render_template("login.html", message=message)


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

    if request.method == "POST":
        text = request.form.get("text", "").strip()
        if text:
            msg_store.add_message(user, text)
        return redirect(url_for("chat"))

    info = all_members[user]
    title = auth.title_for(info["gender"])
    display = auth.display_name(user)

    raw = msg_store.load_messages()
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
            "sender_title": sender_title,
            "sender_display": sender_display,
            "text": m.get("text", ""),
            "time": m.get("time", ""),
        })

    return render_template(
        "chat.html",
        title=title,
        display=display,
        messages=decorated,
    )


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
