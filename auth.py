"""Single-owner login: set a password once, then stay signed in on that browser."""
import datetime
import os
import secrets
import time

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
        if request.endpoint != "login" and not session.get("owner"):
            if request.path.startswith("/api/"):
                return jsonify(error="Login required"), 401
            return redirect("/login")

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
        return PAGE.format(msg=escape(msg), extra=extra, button="Account banayein" if first else "Login")

    def _sign_in():
        session.permanent = True
        session["owner"] = True
        return redirect("/")
