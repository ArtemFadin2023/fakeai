const express = require("express");
const fs = require("fs");
const path = require("path");

const app = express();
app.use(express.json());
app.use(express.static("public"));

const DB = path.join(__dirname, "users.json");

// ===== init =====
if (!fs.existsSync(DB)) {
    fs.writeFileSync(DB, "[]");
}

// ===== utils =====
function loadUsers() {
    try {
        return JSON.parse(fs.readFileSync(DB));
    } catch {
        return [];
    }
}

function saveUsers(users) {
    fs.writeFileSync(DB, JSON.stringify(users, null, 2));
}

// ===== API =====

// 🔍 проверка логина
app.post("/check-login", (req, res) => {
    const { login } = req.body;

    if (!login || login.length < 4) {
        return res.json({ exists: true });
    }

    const users = loadUsers();
    const exists = users.some(u => u.login === login);

    res.json({ exists });
});

// 📝 регистрация
app.post("/register", (req, res) => {
    const { login, password } = req.body;

    if (!login || login.length < 4) {
        return res.json({ status: "error", msg: "login_short" });
    }

    if (!password || password.length < 8) {
        return res.json({ status: "error", msg: "password_short" });
    }

    let users = loadUsers();

    if (users.find(u => u.login === login)) {
        return res.json({ status: "exists" });
    }

    users.push({
        id: Date.now(),
        login,
        password,
        created: Date.now()
    });

    saveUsers(users);

    res.json({ status: "ok" });
});

// 🔐 вход
app.post("/login", (req, res) => {
    const { login, password } = req.body;

    if (!login || !password) {
        return res.json({ status: "error" });
    }

    const users = loadUsers();

    const user = users.find(
        u => u.login === login && u.password === password
    );

    if (!user) {
        return res.json({ status: "error" });
    }

    res.json({ status: "ok" });
});

// 👑 админка (пока без защиты)
app.get("/admin/users", (req, res) => {
    res.json(loadUsers());
});


// ===== AI =====
app.post("/ai", async (req, res) => {
    const { message, mode } = req.body;

    if (!message) {
        return res.json({ error: "no_message" });
    }

    let result;

    try {

        // 🤖 обычный режим
        if (mode === "chat") {
            result = "🤖 Ответ: " + message;
        }

        // 🧠 умный режим
        else if (mode === "smart") {
            result = "🧠 Экспертный анализ: " + message;
        }

        // 📰 проверка новостей
        else if (mode === "news") {
            result = "📰 Проверка: это может быть фейк. Нужны источники.";
        }

        else {
            result = "Неизвестный режим";
        }

        res.json({ result });

    } catch (e) {
        res.json({ error: "server_error" });
    }
});

// ===== запуск =====
app.listen(3000, "0.0.0.0", () => {
    console.log("FakeNewsAI server running");
});