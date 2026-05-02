from factcheck import build_chat, build_smart, build_news
from flask import Flask, request, jsonify, render_template, session, redirect
import sqlite3
from datetime import datetime, timedelta
from flask import send_from_directory
import hashlib, re, json, os, time, secrets, string, shutil

# =========================
# CONFIG
# =========================
ADMIN_PASSWORD = "2703"
ADMIN_LOGIN = "admin"
FREE_MESSAGE_LIMIT = 20

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

def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()[:20]

def is_valid_login(l):
    return 4 <= len(l) <= 30 and re.match(r'^[a-zA-Z0-9_-]+$', l)

def is_valid_password(p):
    return 6 <= len(p) <= 100

def is_valid_email(e):
    return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', e))

def load_json(file):
    if not os.path.exists(file):
        return {}
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_json(file, data):
    try:
        with open(file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving JSON: {e}")

def get_user_dir(user):
    path = os.path.join(HISTORY_DIR, user)
    os.makedirs(path, exist_ok=True)
    return path

def generate_key():
    chars = string.ascii_uppercase + string.digits
    return '-'.join(''.join(secrets.choice(chars) for _ in range(5)) for _ in range(4))

def get_db():
    return sqlite3.connect(os.path.join(BASE_DIR, "users.db"))

def init_db():
    db = get_db()
    db.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        login TEXT UNIQUE, password TEXT, email TEXT,
        created TEXT, last_login TEXT,
        sub_until TEXT, sub_type TEXT,
        message_count INTEGER DEFAULT 0
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS activation_keys(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE, months INTEGER,
        created TEXT, used_by TEXT, used_at TEXT
    )""")
    for col, typ in [("email","TEXT"),("sub_until","TEXT"),("sub_type","TEXT"),("message_count","INTEGER DEFAULT 0")]:
        try: db.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
        except: pass
    db.commit(); db.close()

init_db()

# =========================
# SUBSCRIPTION
# =========================

def get_sub_info(login):
    db = get_db()
    row = db.execute("SELECT sub_until, sub_type, message_count FROM users WHERE login=?", (login,)).fetchone()
    db.close()
    if not row:
        return {"active": False, "until": None, "type": None, "messages_used": 0}
    sub_until, sub_type, msg_count = row
    msg_count = msg_count or 0
    if sub_type == "lifetime":
        return {"active": True, "until": "Бессрочно", "type": "lifetime", "messages_used": msg_count}
    if sub_until:
        try:
            if datetime.strptime(sub_until, "%Y-%m-%d") > datetime.now():
                return {"active": True, "until": sub_until, "type": sub_type, "messages_used": msg_count}
        except: pass
    return {"active": False, "until": sub_until, "type": sub_type, "messages_used": msg_count}

def can_send(login):
    info = get_sub_info(login)
    if info["active"]: return True
    return info["messages_used"] < FREE_MESSAGE_LIMIT

def inc_messages(login):
    db = get_db()
    db.execute("UPDATE users SET message_count=COALESCE(message_count,0)+1 WHERE login=?", (login,))
    db.commit(); db.close()

# =========================
# ADMIN ROUTES
# =========================

@app.route("/admin/users")
def admin_users():
    if not session.get("admin"): return jsonify({"error":"no access"}), 403
    db = get_db()
    rows = db.execute("SELECT login,email,created,last_login,sub_until,sub_type,message_count FROM users ORDER BY created DESC").fetchall()
    db.close()
    result = []
    for r in rows:
        login,email,created,last_login,sub_until,sub_type,msg_count = r
        sub = get_sub_info(login)
        result.append({"login":login,"email":email or "—","created":created,"last_login":last_login or "Никогда",
            "sub_active":sub["active"],"sub_until":sub["until"] or "—","sub_type":sub_type or "—","messages_used":msg_count or 0})
    return jsonify(result)

@app.route("/admin/set_sub", methods=["POST"])
def admin_set_sub():
    if not session.get("admin"): return jsonify({"error":"no access"}), 403
    data = request.get_json() or {}
    login, months = data.get("login"), data.get("months")
    if not login: return jsonify({"status":"error"}), 400
    db = get_db()
    if months is None:
        db.execute("UPDATE users SET sub_until=NULL,sub_type=NULL WHERE login=?", (login,))
    elif months == 0:
        db.execute("UPDATE users SET sub_until=NULL,sub_type='lifetime' WHERE login=?", (login,))
    else:
        until = (datetime.now()+timedelta(days=30*months)).strftime("%Y-%m-%d")
        db.execute("UPDATE users SET sub_until=?,sub_type=? WHERE login=?", (until,f"{months}m",login))
    db.commit(); db.close()
    return jsonify({"status":"ok"})

@app.route("/admin/change_password", methods=["POST"])
def admin_change_pw():
    if not session.get("admin"): return jsonify({"error":"no access"}), 403
    data = request.get_json() or {}
    login, pw = data.get("login"), data.get("password")
    if not login or not pw: return jsonify({"status":"error"}), 400
    db = get_db()
    db.execute("UPDATE users SET password=? WHERE login=?", (hash_password(pw),login))
    db.commit(); db.close()
    return jsonify({"status":"ok"})

@app.route("/admin/delete_user", methods=["POST"])
def admin_delete_user():
    if not session.get("admin"): return jsonify({"error":"no access"}), 403
    login = (request.get_json() or {}).get("login")
    if not login: return jsonify({"status":"error"}), 400
    db = get_db()
    db.execute("DELETE FROM users WHERE login=?", (login,))
    db.commit(); db.close()
    user_dir = os.path.join(HISTORY_DIR, login)
    if os.path.exists(user_dir): shutil.rmtree(user_dir)
    return jsonify({"status":"ok"})

@app.route("/admin/generate_key", methods=["POST"])
def admin_generate_key():
    if not session.get("admin"): return jsonify({"error":"no access"}), 403
    months = (request.get_json() or {}).get("months", 1)
    key = generate_key()
    db = get_db()
    db.execute("INSERT INTO activation_keys(key,months,created) VALUES(?,?,?)",
               (key, months, datetime.now().strftime("%Y-%m-%d %H:%M")))
    db.commit(); db.close()
    return jsonify({"status":"ok","key":key})

@app.route("/admin/keys")
def admin_keys():
    if not session.get("admin"): return jsonify({"error":"no access"}), 403
    db = get_db()
    rows = db.execute("SELECT key,months,created,used_by,used_at FROM activation_keys ORDER BY created DESC").fetchall()
    db.close()
    return jsonify([{"key":r[0],"months":r[1],"created":r[2],"used_by":r[3],"used_at":r[4]} for r in rows])

@app.route("/activate_key", methods=["POST"])
def activate_key():
    user = session.get("user")
    if not user: return jsonify({"status":"error"}), 401
    key = (request.get_json() or {}).get("key","").strip().upper()
    if not key: return jsonify({"status":"error","message":"Введите ключ"}), 400
    db = get_db()
    row = db.execute("SELECT months,used_by FROM activation_keys WHERE key=?", (key,)).fetchone()
    if not row: db.close(); return jsonify({"status":"error","message":"Ключ не найден"}), 404
    months, used_by = row
    if used_by: db.close(); return jsonify({"status":"error","message":"Ключ уже использован"}), 409
    if months == 0:
        db.execute("UPDATE users SET sub_until=NULL,sub_type='lifetime' WHERE login=?", (user,))
    else:
        cur = db.execute("SELECT sub_until,sub_type FROM users WHERE login=?", (user,)).fetchone()
        base = datetime.now()
        if cur and cur[0] and cur[1] != "lifetime":
            try:
                b = datetime.strptime(cur[0], "%Y-%m-%d")
                if b > base: base = b
            except: pass
        until = (base+timedelta(days=30*months)).strftime("%Y-%m-%d")
        db.execute("UPDATE users SET sub_until=?,sub_type=? WHERE login=?", (until,f"{months}m",user))
    db.execute("UPDATE activation_keys SET used_by=?,used_at=? WHERE key=?",
               (user,datetime.now().strftime("%Y-%m-%d %H:%M"),key))
    db.commit(); db.close()
    return jsonify({"status":"ok"})

@app.route("/admin_login", methods=["POST"])
def admin_login():
    data = request.get_json() or {}
    if data.get("login")==ADMIN_LOGIN and data.get("password")==ADMIN_PASSWORD:
        session["admin"] = True
        return jsonify({"status":"ok"})
    return jsonify({"status":"error"}), 401

@app.route("/admin")
def admin():
    if not session.get("admin"): return redirect("/profile")
    return render_template("admin.html")

@app.route("/admin_logout")
def admin_logout():
    session.pop("admin", None); return redirect("/")

# =========================
# AUTH
# =========================

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    login = data.get("login","").strip(); password = data.get("password","")
    if not login or not password: return jsonify({"status":"error","message":"Заполните все поля"}), 400
    db = get_db()
    user = db.execute("SELECT password FROM users WHERE login=?", (login,)).fetchone()
    if not user or user[0] != hash_password(password):
        db.close(); return jsonify({"status":"error","message":"Неверный логин или пароль"}), 401
    db.execute("UPDATE users SET last_login=? WHERE login=?", (datetime.now().strftime("%d.%m.%Y %H:%M"),login))
    db.commit(); db.close()
    session["user"] = login
    return jsonify({"status":"ok","redirect":"/"})

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    login = data.get("login","").strip(); password = data.get("password","")
    if not login or not password: return jsonify({"status":"error","message":"Заполните все поля"}), 400
    if not is_valid_login(login): return jsonify({"status":"error","message":"Логин: 4-30 символов (буквы, цифры, -, _)"}), 400
    if not is_valid_password(password): return jsonify({"status":"error","message":"Пароль минимум 6 символов"}), 400
    db = get_db()
    if db.execute("SELECT id FROM users WHERE login=?", (login,)).fetchone():
        db.close(); return jsonify({"status":"exists","message":"Логин уже занят"}), 409
    try:
        db.execute("INSERT INTO users(login,password,email,created,last_login,message_count) VALUES(?,?,?,?,?,0)",
                   (login,hash_password(password),None,datetime.now().strftime("%d.%m.%Y %H:%M"),None))
        db.commit(); db.close(); session["user"] = login
        return jsonify({"status":"ok","redirect":"/"})
    except Exception as e:
        print(f"Register error: {e}"); return jsonify({"status":"error","message":"Ошибка сервера"}), 500

@app.route('/me')
def me():
    user = session.get("user")
    if not user: return jsonify({"user":None})
    db = get_db()
    row = db.execute("SELECT email FROM users WHERE login=?", (user,)).fetchone()
    db.close()
    sub = get_sub_info(user)
    return jsonify({"user":user,"email":row[0] if row else None,"sub":sub})

@app.route("/login_page")
def login_page():
    if session.get("user"): return redirect("/")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear(); return redirect("/login_page")

# =========================
# PROFILE
# =========================

@app.route("/profile")
def profile():
    if not session.get("user"): return redirect("/login_page")
    return render_template("profile.html")

@app.route("/change_password", methods=["POST"])
def change_password():
    user = session.get("user")
    if not user: return jsonify({"status":"error"}), 401
    data = request.get_json() or {}
    current = data.get("current_password",""); new_pass = data.get("new_password","")
    db = get_db()
    result = db.execute("SELECT password FROM users WHERE login=?", (user,)).fetchone()
    if not result or result[0] != hash_password(current):
        db.close(); return jsonify({"status":"error","message":"Неверный текущий пароль"}), 401
    if not is_valid_password(new_pass):
        db.close(); return jsonify({"status":"error","message":"Пароль минимум 6 символов"}), 400
    db.execute("UPDATE users SET password=? WHERE login=?", (hash_password(new_pass),user))
    db.commit(); db.close()
    return jsonify({"status":"ok"})

@app.route("/change_email", methods=["POST"])
def change_email():
    user = session.get("user")
    if not user: return jsonify({"status":"error"}), 401
    email = (request.get_json() or {}).get("email","").strip().lower()
    if not email: return jsonify({"status":"error","message":"Введите email"}), 400
    if not is_valid_email(email): return jsonify({"status":"error","message":"Неверный формат email"}), 400
    db = get_db()
    if db.execute("SELECT login FROM users WHERE email=? AND login!=?", (email,user)).fetchone():
        db.close(); return jsonify({"status":"error","message":"Email уже используется"}), 409
    db.execute("UPDATE users SET email=? WHERE login=?", (email,user))
    db.commit(); db.close()
    return jsonify({"status":"ok"})

# =========================
# FILES
# =========================

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    if ".." in filename or "/" in filename: return "Forbidden", 403
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/upload_image", methods=["POST"])
def upload_image():
    if "image" not in request.files: return jsonify({"error":"no file"}), 400
    file = request.files["image"]
    if not file.filename: return jsonify({"error":"empty"}), 400
    if not file.filename.lower().endswith(('.png','.jpg','.jpeg','.gif','.webp')):
        return jsonify({"error":"invalid format"}), 400
    try:
        filename = f"{int(time.time())}_{abs(hash(file.filename))}.png"
        file.save(os.path.join(UPLOAD_FOLDER, filename))
        return jsonify({"path":"/uploads/"+filename})
    except Exception as e:
        return jsonify({"error":"upload failed"}), 500

# =========================
# CHAT
# =========================

@app.route("/chats")
def chats():
    user = session.get("user")
    if not user: return jsonify([])
    folder = get_user_dir(user)
    result = []
    for f in os.listdir(folder):
        fpath = os.path.join(folder, f)
        try: mtime = os.path.getmtime(fpath)
        except: mtime = 0
        data = load_json(fpath)
        if isinstance(data, dict):
            title = data.get("title"); messages = data.get("messages", [])
        else:
            title = None; messages = data
        result.append({"id":f,"title":title,"mtime":mtime,"pinned":f.startswith("pin_"),"message_count":len(messages)})
    result.sort(key=lambda x: (-x["pinned"],-x["mtime"]))
    return jsonify(result)

@app.route("/new_chat", methods=["POST"])
def new_chat():
    user = session.get("user")
    if not user: return jsonify({"status":"error"}), 401
    name = f"chat_{int(time.time())}.json"
    save_json(os.path.join(get_user_dir(user), name), {"title":None,"messages":[]})
    return jsonify({"status":"ok","chat":name})

@app.route("/history/<chat>")
def history_chat(chat):
    user = session.get("user")
    if not user: return jsonify([])
    data = load_json(os.path.join(get_user_dir(user), chat))
    if isinstance(data, dict): return jsonify(data.get("messages",[])[-50:])
    return jsonify((data or [])[-50:])

@app.route("/delete_chat", methods=["POST"])
def delete_chat():
    user = session.get("user"); chat = (request.json or {}).get("chat")
    if not user or not chat: return jsonify({"status":"error"}), 400
    path = os.path.join(get_user_dir(user), chat)
    if os.path.exists(path): os.remove(path)
    return jsonify({"status":"ok"})

@app.route("/clear_chat", methods=["POST"])
def clear_chat():
    user = session.get("user"); chat = (request.json or {}).get("chat")
    if not user or not chat: return jsonify({"status":"error"}), 400
    file = os.path.join(get_user_dir(user), chat)
    data = load_json(file)
    title = data.get("title") if isinstance(data, dict) else None
    save_json(file, {"title":title,"messages":[]})
    return jsonify({"status":"ok"})

@app.route("/pin_chat", methods=["POST"])
def pin_chat():
    user = session.get("user"); chat = (request.json or {}).get("chat")
    if not user or not chat: return jsonify({"status":"error"}), 400
    old = os.path.join(get_user_dir(user), chat)
    new_name = chat.replace("pin_","") if chat.startswith("pin_") else "pin_"+chat
    try:
        os.rename(old, os.path.join(get_user_dir(user), new_name))
        return jsonify({"status":"ok","chat":new_name})
    except: return jsonify({"status":"error"}), 500

# =========================
# AI
# =========================

@app.route("/ai", methods=["POST"])
def ai():
    user = session.get("user")
    if not user: return jsonify({"result":"❌ Авторизуйся"}), 401
    if not can_send(user): return jsonify({"result":"LIMIT","limit_reached":True}), 200

    data = request.get_json() or {}
    text = data.get("message","").strip(); mode = data.get("mode","chat"); chat = data.get("chat")
    if not text: return jsonify({"result":"❌ Пусто"}), 400
    if not chat: return jsonify({"result":"❌ Выбери чат"}), 400
    if len(text) > 5000: return jsonify({"result":"❌ Слишком длинное"}), 400

    file = os.path.join(get_user_dir(user), chat)
    raw = load_json(file)
    if isinstance(raw, dict):
        chat_title = raw.get("title"); history = raw.get("messages", [])
    else:
        chat_title = None; history = raw or []

    context = "".join(f"User: {m.get('user','')}\nAI: {m.get('bot','')}\n" for m in history[-30:])
    full_prompt = context + f"User: {text}\nAI:"

    try:
        if mode == "chat": result = build_chat(full_prompt)
        elif mode == "smart": result = build_smart(full_prompt)
        elif mode == "news": result = build_news(full_prompt)
        else: result = build_chat(full_prompt)
        if not result or result.startswith("⚠️"):
            result = "⚠️ Сервис временно недоступен. Попробуй позже."
    except Exception as e:
        print(f"AI ERROR: {e}"); result = "⚠️ Ошибка обработки"

    new_title = chat_title
    if not chat_title and len(history) == 0:
        try:
            t = build_chat(f"Придумай короткое название (3-5 слов, без кавычек) для чата: '{text[:150]}'. Только название.")
            if t: new_title = t.strip().strip('"').strip("'")[:50]
        except: pass

    history.append({"mode":mode,"user":text,"bot":result,"time":int(time.time())})
    save_json(file, {"title":new_title,"messages":history[-100:]})
    inc_messages(user)

    sub = get_sub_info(user)
    messages_left = max(0, FREE_MESSAGE_LIMIT - sub["messages_used"] - 1) if not sub["active"] else None
    return jsonify({"result":result,"chat_title":new_title,"messages_left":messages_left,"sub_active":sub["active"]})

# =========================
# MAIN
# =========================

@app.route("/")
def home():
    if not session.get("user"): return redirect("/login_page")
    return render_template("index.html")

@app.route("/health")
def health(): return jsonify({"status":"ok"})

@app.errorhandler(404)
def not_found(e): return jsonify({"error":"Not found"}), 404

@app.errorhandler(500)
def server_error(e): return jsonify({"error":"Server error"}), 500

if __name__ == "__main__":
    print("🚀 SERVER STARTED ON http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)