"""Single-owner login: set a password once, then stay signed in on that browser."""
import datetime
import os
import secrets
import smtplib
import time
from email.message import EmailMessage

from flask import jsonify, redirect, request, session
from markupsafe import escape
from werkzeug.security import check_password_hash, generate_password_hash

PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dhun login</title><body style="font-family:system-ui;max-width:340px;margin:60px auto;padding:0 16px">
<h2>Dhun</h2><p>{msg}</p><form method="post">{extra}
<input type="password" name="password" placeholder="Password (min 8)" required style="width:100%;padding:12px;margin:6px 0">
<button style="width:100%;padding:12px">{button}</button></form>"""


def _private_write(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)


RESET_PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dhun password reset</title><body style="font-family:system-ui;max-width:340px;margin:60px auto;padding:0 16px">
<h2>Password reset</h2><p>{msg}</p>
<form method="post">{send}</form>
<form method="post"><input name="code" placeholder="Reset code ya Colab ka setup code" required style="width:100%;padding:12px">
<input type="password" name="password" placeholder="Naya password (min 8)" required style="width:100%;padding:12px;margin:6px 0">
<button style="width:100%;padding:12px">Password badlein</button></form><p><a href="/login">Login par wapas</a></p>"""


def _send_code(code):
    """Mail the code to the owner's pre-set address only (never to an address typed on the page)."""
    user, key = os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"]
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = "Dhun password reset code", user, os.environ.get("RESET_EMAIL") or user
    msg.set_content(f"Dhun reset code: {code}\n15 minute tak chalega. Aapne nahi maanga to ise ignore karein.")
    with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST", "smtp.gmail.com"), int(os.environ.get("SMTP_PORT", "465")),
                          timeout=30) as s:
        s.login(user, key)
        s.send_message(msg)


def init_auth(app, data_dir):
    key_file = os.path.join(data_dir, "secret.key")
    pw_file = os.path.join(data_dir, "password.hash")
    if not os.path.exists(key_file):
        _private_write(key_file, secrets.token_hex(32))
    with open(key_file) as f:
        app.secret_key = f.read()
    app.config.update(PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=3650),
                      SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True)
    setup_code = os.environ.get("SETUP_CODE") or secrets.token_hex(4)
    if not os.path.exists(pw_file):
        print(f"DHUN SETUP CODE: {setup_code}", flush=True)

    @app.before_request
    def require_login():
        if request.endpoint not in ("login", "reset") and not session.get("owner"):
            if request.path.startswith("/api/"):
                return jsonify(error="Login required"), 401
            return redirect("/login")

    state = {"code": None, "expires": 0, "sent": 0, "fails": 0, "locked": 0}

    @app.route("/reset", methods=["GET", "POST"])
    def reset():
        if not os.path.exists(pw_file):
            return redirect("/login")
        mail = bool(os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"))
        msg = ("Email par code mangayein, ya Colab mein dikha setup code dalein." if mail
               else "Email set nahi hai. Colab mein dikha setup code dalein.")
        now = time.time()
        if request.method == "POST" and request.form.get("action") == "send" and mail:
            if now - state["sent"] < 60:
                msg = "Ek minute baad dobara mangayein."
            else:
                state.update(sent=now, code=f"{secrets.randbelow(10**8):08d}", expires=now + 900)
                try:
                    _send_code(state["code"])
                    msg = "Code aapke set kiye hue email par bhej diya gaya hai."
                except Exception as e:  # noqa
                    print("Reset mail failed:", type(e).__name__, flush=True)
                    msg = "Email nahi gaya. Colab ka setup code istemal karein."
        elif request.method == "POST":
            code, pw = request.form.get("code", "").strip().encode(), request.form.get("password", "")
            ok_mail = bool(state["code"]) and now < state["expires"] and secrets.compare_digest(code, state["code"].encode())
            if now < state["locked"]:
                msg = "Bahut galat koshish. 15 minute baad try karein."
            elif not (ok_mail or secrets.compare_digest(code, setup_code.encode())):
                time.sleep(2)
                state["fails"] += 1
                if state["fails"] >= 5:
                    state.update(fails=0, code=None, locked=now + 900)
                msg = "Code galat ya purana hai."
            elif len(pw) < 8:
                msg = "Password kam se kam 8 akshar ka rakhein."
            else:
                _private_write(pw_file, generate_password_hash(pw))
                state.update(code=None, fails=0)
                return _sign_in()
        send = ('<button name="action" value="send" style="width:100%;padding:12px;margin-bottom:10px">'
                "Email par code bhejein</button>") if mail else ""
        return RESET_PAGE.format(msg=escape(msg), send=send)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        first = not os.path.exists(pw_file)
        msg = "Pehli baar: setup code (server log mein) aur naya password dalein." if first else "Password dalein."
        if request.method == "POST":
            pw = request.form.get("password", "")
            if first:
                if not secrets.compare_digest(request.form.get("code", "").encode(), setup_code.encode()):
                    msg = "Setup code galat hai."
                elif len(pw) < 8:
                    msg = "Password kam se kam 8 akshar ka rakhein."
                else:
                    _private_write(pw_file, generate_password_hash(pw))
                    return _sign_in()
            else:
                with open(pw_file) as f:
                    if check_password_hash(f.read(), pw):
                        return _sign_in()
                time.sleep(2)   # slow down guessing
                msg = "Password galat hai."
        extra = '<input name="code" placeholder="Setup code" required style="width:100%;padding:12px">' if first else ""
        link = "" if first else '<p><a href="/reset">Password bhool gaye?</a></p>'
        return PAGE.format(msg=escape(msg), extra=extra, button="Account banayein" if first else "Login") + link

    def _sign_in():
        session.permanent = True
        session["owner"] = True
        return redirect("/")
