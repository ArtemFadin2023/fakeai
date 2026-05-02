from factcheck import build_chat, build_smart, build_news
from flask import Flask, request, jsonify, render_template, session, redirect
import sqlite3
from datetime import datetime
from flask import send_from_directory
import hashlib
import re

import json
import os
import time

# =========================
# CONFIG
# =========================
ADMIN_PASSWORD = "2703"
ADMIN_LOGIN = "admin"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)

app.secret_key = "super_secret_key_123_change_in_production"

HISTORY_DIR = os.path.join(BASE_DIR, "history")

if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)

# =========================
# UTILITIES
# =========================

def hash_password(password):
    """Хэшировать пароль с солью"""
    return hashlib.sha256(password.encode()).hexdigest()[:20]

def is_valid_login(login):
    """Проверить валидность логина"""
    return len(login) >= 4 and len(login) <= 30 and re.match(r'^[a-zA-Z0-9_-]+$', login)

def is_valid_password(password):
    """Проверить валидность пароля"""
    return len(password) >= 6 and len(password) <= 100

def get_user_history_file(user):
    return os.path.join(HISTORY_DIR, f"{user}.json")

def load_json(file):
    if not os.path.exists(file):
        return []
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_json(file, data):
    try:
        with open(file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving JSON: {e}")

def get_user_dir(user):
    path = os.path.join(HISTORY_DIR, user)
    if not os.path.exists(path):
        os.makedirs(path)
    return path

# =========================
# DATABASE
# =========================

def get_db():
    return sqlite3.connect(os.path.join(BASE_DIR, "users.db"))

def init_db():
    db = get_db()
    db.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        login TEXT UNIQUE,
        password TEXT,
        created TEXT,
        last_login TEXT
    )
    """)
    db.commit()
    db.close()

init_db()

# =========================
# ROUTES - AUTH
# =========================

@app.route("/admin/users")
def admin_users():
    if not session.get("admin"):
        return jsonify({"error": "no access"}), 403

    db = get_db()
    rows = db.execute("SELECT login, created, last_login FROM users ORDER BY created DESC").fetchall()

    return jsonify([
        {
            "login": r[0],
            "created": r[1],
            "last_login": r[2] or "Никогда"
        }
        for r in rows
    ])

@app.route("/admin_login", methods=["POST"])
def admin_login():
    data = request.get_json() or {}

    if data.get("login") == ADMIN_LOGIN and data.get("password") == ADMIN_PASSWORD:
        session["admin"] = True
        return jsonify({"status": "ok"})

    return jsonify({"status": "error"}), 401

@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/profile")
    return render_template("admin.html")

@app.route("/admin_logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/")

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}

    login = data.get("login", "").strip()
    password = data.get("password", "")

    if not login or not password:
        return jsonify({"status": "error", "message": "Заполните все поля"}), 400

    db = get_db()
    user = db.execute(
        "SELECT password FROM users WHERE login=?",
        (login,)
    ).fetchone()

    if not user or user[0] != hash_password(password):
        return jsonify({"status": "error", "message": "Неверный логин или пароль"}), 401

    # Update last login
    db.execute(
        "UPDATE users SET last_login=? WHERE login=?",
        (datetime.now().strftime("%d.%m.%Y %H:%M"), login)
    )
    db.commit()
    db.close()

    session["user"] = login
    return jsonify({"status": "ok", "redirect": "/"})

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json() or {}

    login = data.get("login", "").strip()
    password = data.get("password", "")

    if not login or not password:
        return jsonify({"status": "error", "message": "Заполните все поля"}), 400

    if not is_valid_login(login):
        return jsonify({"status": "error", "message": "Логин: 4-30 символов (буквы, цифры, -, _)"}), 400

    if not is_valid_password(password):
        return jsonify({"status": "error", "message": "Пароль минимум 6 символов"}), 400

    db = get_db()
    exists = db.execute("SELECT id FROM users WHERE login=?", (login,)).fetchone()

    if exists:
        return jsonify({"status": "exists", "message": "Этот логин уже занят"}), 409

    try:
        db.execute(
            "INSERT INTO users(login, password, created, last_login) VALUES(?,?,?,?)",
            (login, hash_password(password), datetime.now().strftime("%d.%m.%Y %H:%M"), None)
        )
        db.commit()
        db.close()

        session["user"] = login
        return jsonify({"status": "ok", "redirect": "/"})

    except Exception as e:
        print(f"Register error: {e}")
        return jsonify({"status": "error", "message": "Ошибка сервера"}), 500

@app.route('/me')
def me():
    user = session.get("user")
    if not user:
        return jsonify({"user": None})
    return jsonify({"user": user})

@app.route("/login_page")
def login_page():
    if session.get("user"):
        return redirect("/")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login_page")

# =========================
# ROUTES - PROFILE
# =========================

@app.route("/profile")
def profile():
    if not session.get("user"):
        return redirect("/login_page")
    return render_template("profile.html")

@app.route("/change_password", methods=["POST"])
def change_password():
    user = session.get("user")
    if not user:
        return jsonify({"status": "error"}), 401

    data = request.get_json() or {}
    current = data.get("current_password", "")
    new_pass = data.get("new_password", "")

    db = get_db()
    result = db.execute("SELECT password FROM users WHERE login=?", (user,)).fetchone()

    if not result or result[0] != hash_password(current):
        return jsonify({"status": "error", "message": "Неверный текущий пароль"}), 401

    if not is_valid_password(new_pass):
        return jsonify({"status": "error", "message": "Пароль минимум 6 символов"}), 400

    db.execute("UPDATE users SET password=? WHERE login=?", (hash_password(new_pass), user))
    db.commit()
    db.close()

    return jsonify({"status": "ok"})

# =========================
# ROUTES - FILES & UPLOADS
# =========================

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    # Защита от path traversal
    if ".." in filename or "/" in filename:
        return "Forbidden", 403
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/upload_image", methods=["POST"])
def upload_image():
    if "image" not in request.files:
        return jsonify({"error": "no file"}), 400

    file = request.files["image"]

    if file.filename == "":
        return jsonify({"error": "empty"}), 400

    # Проверить расширение
    if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
        return jsonify({"error": "invalid format"}), 400

    try:
        filename = f"{int(time.time())}_{hash(file.filename)}.png"
        path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(path)
        return jsonify({"path": "/uploads/" + filename})
    except Exception as e:
        print(f"Upload error: {e}")
        return jsonify({"error": "upload failed"}), 500

# =========================
# ROUTES - CHAT
# =========================

@app.route("/chats")
def chats():
    user = session.get("user")
    if not user:
        return jsonify([])

    folder = get_user_dir(user)
    files = os.listdir(folder) if os.path.exists(folder) else []

    pinned = [f for f in files if f.startswith("pin_")]
    normal = [f for f in files if not f.startswith("pin_")]

    return jsonify(pinned + normal)

@app.route("/new_chat", methods=["POST"])
def new_chat():
    user = session.get("user")
    if not user:
        return jsonify({"status": "error"}), 401

    folder = get_user_dir(user)
    name = f"chat_{int(time.time())}.json"
    path = os.path.join(folder, name)

    save_json(path, [])
    return jsonify({"status": "ok", "chat": name})

@app.route("/history/<chat>")
def history_chat(chat):
    user = session.get("user")
    if not user:
        return jsonify([])

    file = os.path.join(get_user_dir(user), chat)
    return jsonify(load_json(file)[-50:])

@app.route("/delete_chat", methods=["POST"])
def delete_chat():
    user = session.get("user")
    chat = request.json.get("chat")

    if not user or not chat:
        return jsonify({"status": "error"}), 400

    path = os.path.join(get_user_dir(user), chat)
    if os.path.exists(path):
        os.remove(path)

    return jsonify({"status": "ok"})

@app.route("/clear_chat", methods=["POST"])
def clear_chat():
    user = session.get("user")
    chat = request.json.get("chat")

    if not user or not chat:
        return jsonify({"status": "error"}), 400

    file = os.path.join(get_user_dir(user), chat)
    save_json(file, [])

    return jsonify({"status": "ok"})

@app.route("/pin_chat", methods=["POST"])
def pin_chat():
    user = session.get("user")
    chat = request.json.get("chat")

    if not user or not chat:
        return jsonify({"status": "error"}), 400

    old = os.path.join(get_user_dir(user), chat)
    new_name = chat.replace("pin_", "") if chat.startswith("pin_") else "pin_" + chat
    new = os.path.join(get_user_dir(user), new_name)

    try:
        os.rename(old, new)
        return jsonify({"status": "ok", "chat": new_name})
    except:
        return jsonify({"status": "error"}), 500

# =========================
# ROUTES - AI
# =========================

@app.route("/ai", methods=["POST"])
def ai():
    user = session.get("user")
    if not user:
        return jsonify({"result": "❌ Авторизуйся"}), 401

    data = request.get_json() or {}
    text = data.get("message", "").strip()
    mode = data.get("mode", "chat")
    chat = data.get("chat")

    if not text:
        return jsonify({"result": "❌ Пусто"}), 400

    if not chat:
        return jsonify({"result": "❌ Выбери чат"}), 400

    # Limit message length
    if len(text) > 5000:
        return jsonify({"result": "❌ Сообщение слишком длинное"}), 400

    file = os.path.join(get_user_dir(user), chat)
    history = load_json(file)

    # Build context
    context_messages = history[-30:]
    context_text = ""

    for m in context_messages:
        context_text += f"User: {m.get('user','')}\nAI: {m.get('bot','')}\n"

    full_prompt = context_text + f"User: {text}\nAI:"

    try:
        if mode == "chat":
            result = build_chat(full_prompt)
        elif mode == "smart":
            result = build_smart(full_prompt)
        elif mode == "news":
            result = build_news(full_prompt)
        else:
            result = build_chat(full_prompt)

        if not result or result.startswith("⚠️"):
            result = "⚠️ Сервис временно недоступен. Попробуй позже."

    except Exception as e:
        print(f"AI ERROR: {e}")
        result = "⚠️ Ошибка обработки"

    # Save to history
    history.append({
        "mode": mode,
        "user": text,
        "bot": result,
        "time": int(time.time())
    })

    save_json(file, history[-100:])
    return jsonify({"result": result})

# =========================
# MAIN PAGES
# =========================

@app.route("/")
def home():
    if not session.get("user"):
        return redirect("/login_page")
    return render_template("index.html")

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

# =========================
# ERROR HANDLERS
# =========================

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Server error"}), 500

# =========================
# RUN
# =========================

if __name__ == "__main__":
    print("🚀 SERVER STARTED ON http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)