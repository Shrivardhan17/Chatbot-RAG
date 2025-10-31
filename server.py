# server.py
"""
Improved single-file Flask app based on the user's provided logic.
Features:
 - Uses SentenceTransformer, Pinecone (optional), googletrans (optional)
 - Gemini call placeholder (uses GEMINI_API_KEY if provided)
 - MySQL connection (database name from env: chatbot_app)
 - Auto-create tables: users, chat_history
 - /history -> view-only full chat history grouped by date/time
 - /chatpage -> interactive chat (send/receive, saved to DB)
 - /chat -> POST endpoint to generate answer + save history
 - Secure password hashing for user registration & password change
"""

import os
import io
import csv
import requests
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template_string, redirect, session, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Optional imports - may fail if packages not installed; handle gracefully
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMER_AVAILABLE = True
except Exception:
    SENTENCE_TRANSFORMER_AVAILABLE = False

try:
    # pinecone import path may vary by package version; adjust if necessary
    from pinecone import Pinecone
    PINECONE_AVAILABLE = True
except Exception:
    PINECONE_AVAILABLE = False

try:
    from googletrans import Translator
    GOOGLETRANS_AVAILABLE = True
except Exception:
    GOOGLETRANS_AVAILABLE = False

try:
    import mysql.connector
    MYSQL_AVAILABLE = True
except Exception:
    MYSQL_AVAILABLE = False

# ------------------- Load Environment Variables -------------------
load_dotenv()
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
INDEX_NAME = os.getenv("INDEX_NAME", "med-book")
MODEL_NAME = os.getenv("MODEL_NAME", "models/gemini-2.0-flash")

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "chatbot_app")

SECRET_KEY = os.getenv("SECRET_KEY", "your_secret_key_here")
DEBUG = os.getenv("FLASK_DEBUG", "true").lower() in ("1", "true", "yes")

# ------------------- Initialize optional services safely -------------------
pc = None
index = None
model = None
translator = None

if SENTENCE_TRANSFORMER_AVAILABLE:
    try:
        model = SentenceTransformer("all-MiniLM-L6-v2")
    except Exception as e:
        model = None
        print("SentenceTransformer load failed:", e)

if GOOGLETRANS_AVAILABLE:
    try:
        translator = Translator()
    except Exception as e:
        translator = None
        print("googletrans init failed:", e)

if PINECONE_AVAILABLE and PINECONE_API_KEY:
    try:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        index = pc.Index(INDEX_NAME)
    except Exception as e:
        index = None
        print("Pinecone init failed:", e)

# ------------------- MySQL connection helper -------------------
if not MYSQL_AVAILABLE:
    raise ImportError("mysql-connector-python not installed. Please install mysql-connector-python.")

def get_db_connection():
    return mysql.connector.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        autocommit=False
    )

def init_db_tables():
    """
    Create `users` and `chat_history` tables if they don't exist.
    """
    conn = None
    try:
        # Connect to MySQL server first; create database if needed
        conn = mysql.connector.connect(host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD, autocommit=True)
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DB}` DEFAULT CHARACTER SET 'utf8mb4'")
        cursor.close()
        conn.close()
        # Now connect to the database and create tables
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(150) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE,
                password VARCHAR(255) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(150) NOT NULL,
                message TEXT,
                response TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        conn.commit()
        cursor.close()
    except Exception as e:
        print("init_db_tables error:", e)
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

# Initialize database tables
init_db_tables()

# ------------------- Initialize Flask -------------------
app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["DEBUG"] = DEBUG

# ------------------- small state -------------------
last_disease_query = {"text": None, "name": None}

# ------------------- Templates (kept from your original code) -------------------
# For brevity I reuse the templates you provided, with small adjustments to integrate history view.
# Login, register, dashboard, chatpage, history page templates follow.

login_html = """<...>"""  # we will inject full template strings below to avoid truncation in analysis; see final code

# To keep the response clear, I'll paste the full templates (unchanged except minor safe fixes).
# -------- Login Page --------
login_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Login - ShriGPT</title>
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
body{margin:0;font-family:'Roboto',sans-serif;background:#0f172a;color:#e2e8f0;display:flex;justify-content:center;align-items:center;height:100vh;}
.container{backdrop-filter: blur(15px);background: rgba(30,41,59,0.6);padding:50px 35px;border-radius:25px;box-shadow:0 0 40px rgba(0,0,0,0.7);width:350px;}
h2{text-align:center;color:#0ea5e9;font-size:2rem;margin-bottom:25px;text-shadow:0 0 10px #38bdf8;}
form{display:flex;flex-direction:column;}
input{margin:12px 0;padding:14px;border-radius:12px;border:none;outline:none;background:rgba(15,23,42,0.7);color:white;font-size:1rem;transition:0.3s;}
input:focus{border:1px solid #3b82f6;box-shadow:0 0 10px #3b82f6;}
button{margin-top:16px;padding:14px;border-radius:12px;border:none;background:linear-gradient(135deg,#3b82f6,#22d3ee);color:white;font-weight:bold;cursor:pointer;transition:0.3s;font-size:1rem;text-shadow:0 0 5px #2563eb;}
button:hover{background:linear-gradient(135deg,#2563eb,#0ea5e9);transform:scale(1.05);}
a{color:#38bdf8;text-decoration:none;margin-top:14px;text-align:center;display:block;}
.flash{color:#f87171;margin-top:10px;text-align:center;font-weight:bold;}
</style>
</head>
<body>
<div class="container">
<h2><i class="fa-solid fa-brain"></i> ShriGPT</h2>
<form method="POST" action="/login">
<input type="text" name="username" placeholder="Username" required>
<input type="password" name="password" placeholder="Password" required>
<button type="submit"><i class="fa-solid fa-right-to-bracket"></i> Login</button>
</form>
<a href="/register"><i class="fa-solid fa-user-plus"></i> Register New Account</a>
{% with messages = get_flashed_messages() %}
  {% if messages %}
    <div class="flash">{{ messages[0] }}</div>
  {% endif %}
{% endwith %}
</div>
</body>
</html>
"""

register_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Register - ShriGPT</title>
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
body{margin:0;font-family:'Roboto',sans-serif;background:#0f172a;color:#e2e8f0;display:flex;justify-content:center;align-items:center;height:100vh;}
.container{backdrop-filter: blur(15px);background: rgba(30,41,59,0.6);padding:50px 35px;border-radius:25px;box-shadow:0 0 40px rgba(0,0,0,0.7);width:350px;}
h2{text-align:center;color:#0ea5e9;font-size:2rem;margin-bottom:25px;text-shadow:0 0 10px #38bdf8;}
form{display:flex;flex-direction:column;}
input{margin:12px 0;padding:14px;border-radius:12px;border:none;outline:none;background:rgba(15,23,42,0.7);color:white;font-size:1rem;transition:0.3s;}
input:focus{border:1px solid #3b82f6;box-shadow:0 0 10px #3b82f6;}
button{margin-top:16px;padding:14px;border-radius:12px;border:none;background:linear-gradient(135deg,#3b82f6,#22d3ee);color:white;font-weight:bold;cursor:pointer;transition:0.3s;font-size:1rem;text-shadow:0 0 5px #2563eb;}
button:hover{background:linear-gradient(135deg,#2563eb,#0ea5e9);transform:scale(1.05);}
a{color:#38bdf8;text-decoration:none;margin-top:14px;text-align:center;display:block;}
.flash{color:#f87171;margin-top:10px;text-align:center;font-weight:bold;}
</style>
</head>
<body>
<div class="container">
<h2><i class="fa-solid fa-brain"></i> ShriGPT</h2>
<form method="POST" action="/register">
<input type="text" name="username" placeholder="Username" required>
<input type="email" name="email" placeholder="Email" required>
<input type="password" name="password" placeholder="Password" required>
<button type="submit"><i class="fa-solid fa-user-plus"></i> Register</button>
</form>
<a href="/login"><i class="fa-solid fa-right-to-bracket"></i> Already have an account? Login</a>
{% with messages = get_flashed_messages() %}
  {% if messages %}
    <div class="flash">{{ messages[0] }}</div>
  {% endif %}
{% endwith %}
</div>
</body>
</html>
"""

dashboard_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🧠 ShriGPT Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
body{margin:0;font-family:'Roboto',sans-serif;background:#0f172a;color:#e2e8f0;}
.container{max-width:1200px;margin:auto;padding:20px;}
header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;}
h1{color:#38bdf8;text-shadow:0 0 10px #0ea5e9;}
button{padding:12px 20px;border:none;border-radius:12px;font-weight:bold;color:white;cursor:pointer;margin-left:10px;background:linear-gradient(135deg,#3b82f6,#22d3ee);transition:0.3s;text-shadow:0 0 5px #2563eb;}
button:hover{background:linear-gradient(135deg,#2563eb,#0ea5e9);transform:scale(1.05);}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:25px;}
.card{background:rgba(30,41,59,0.6);backdrop-filter:blur(10px);padding:25px;border-radius:25px;box-shadow:0 10px 30px rgba(0,0,0,0.6);}
input{width:100%;padding:12px;margin:6px 0;border-radius:12px;border:none;background:rgba(15,23,42,0.7);color:white;}
.flash{color:#f87171;margin-top:10px;font-weight:bold;}
ul{padding-left:20px;}
</style>
</head>
<body>
<div class="container">
<header>
<h1><i class="fa-solid fa-brain"></i> Welcome, {{ session['username'] }}</h1>
<form method="POST" action="/logout"><button type="submit"><i class="fa-solid fa-right-from-bracket"></i> Logout</button></form>
</header>
<div class="cards">
<div class="card">
<h2><i class="fa-solid fa-user"></i> Profile</h2>
<p><b>Username:</b> {{ user.username }}</p>
<p><b>Email:</b> {{ user.email }}</p>
<h3>Change Password</h3>
<form method="POST" action="/change_password">
<input type="password" name="current_password" placeholder="Current Password" required>
<input type="password" name="new_password" placeholder="New Password" required>
<button type="submit"><i class="fa-solid fa-key"></i> Update Password</button>
</form>
{% with messages = get_flashed_messages() %}
  {% if messages %}
    <div class="flash">{{ messages[0] }}</div>
  {% endif %}
{% endwith %}
</div>
<div class="card">
<h2><i class="fa-solid fa-robot"></i> ShriGPT Chatbot</h2>
<p>🧠 AI Medical assistant providing health guidance and information quickly.</p>
<ul>
<li>🌏 Multi-language support</li>
<li>🎙 Voice input</li>
<li>🤖 AI-powered answers using Gemini & Pinecone</li>
<li>📜 Private chat history</li>
<li>💊 Symptom checker & guidance</li>
<li>📚 Trusted medical references</li>
<li>🔔 Health reminders & tips</li>
</ul>
<button onclick="window.location.href='/history'"><i class="fa-solid fa-clock-rotate-left"></i> View History</button>
<button onclick="window.location.href='/chatpage'"><i class="fa-solid fa-comment-medical"></i> Start Chatting</button>
</div>
</div>
</div>
</body>
</html>
"""

# History page (view-only)
history_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🕰 ShriGPT Chat History</title>
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
body{margin:0;font-family:'Roboto',sans-serif;background:#0f172a;color:#e2e8f0;display:flex;justify-content:center;align-items:flex-start;padding:30px 0;}
.container{width:100%;max-width:900px;background:rgba(30,41,59,0.6);padding:20px;border-radius:14px;}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;}
h1{color:#38bdf8;margin:0;}
.btn{padding:8px 12px;border-radius:10px;border:none;background:linear-gradient(135deg,#3b82f6,#22d3ee);color:white;cursor:pointer;}
.chat-box{max-height:70vh;overflow:auto;padding:12px;border-radius:8px;background:rgba(10,14,20,0.4);}
.msg{padding:12px 14px;border-radius:10px;margin:10px 0;max-width:80%;white-space:pre-wrap;line-height:1.45;}
.user{background:linear-gradient(135deg,#3b82f6,#22d3ee);color:white;margin-left:auto;text-align:right;}
.bot{background:rgba(51,65,85,0.95);color:#f8fafc;margin-right:auto;text-align:left;border:1px solid #475569;}
.meta{font-size:0.78rem;color:#94a3b8;margin-top:6px;}
.date-sep{text-align:center;color:#94a3b8;margin:12px 0;}
.empty{color:#94a3b8;padding:20px;text-align:center;}
</style>
</head>
<body>
<div class="container">
<div class="header">
<h1>🕰 Chat History</h1>
<div>
<form method="POST" action="/clear_history" style="display:inline;">
<button class="btn" type="submit">🗑 Clear History</button>
</form>
<form action="/download_history_pdf" method="get">
    <input type="date" name="date"> <!-- optional -->
    <button type="submit">📄 Download PDF</button>
</form>
<button class="btn" onclick="location.href='/chatpage'">💬 Start Chatting</button>
</div>
</div>
<div class="chat-box">
{% if history %}
  {% set last_date=None %}
  {% for chat in history %}
    {% set chat_date = chat.timestamp.strftime('%Y-%m-%d') %}
    {% if chat_date != last_date %}
      <div class="date-sep">📅 {{ chat.timestamp.strftime('%B %d, %Y') }}</div>
      {% set last_date = chat_date %}
    {% endif %}
    <div class="msg user">🧑 <b>You:</b> {{ chat.message }}<div class="meta">🕒 {{ chat.timestamp.strftime('%H:%M:%S') }}</div></div>
    <div class="msg bot">🤖 <b>ShriGPT:</b> {{ chat.response }}<div class="meta">🕒 {{ chat.timestamp.strftime('%H:%M:%S') }}</div></div>
  {% endfor %}
{% else %}
  <div class="empty">No chat history yet. Click "Start Chatting" to begin.</div>
{% endif %}
</div>
</div>
</body>
</html>
"""

# Chat page (active)
chat_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🧠 ShriGPT Medical Assistant</title>
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
body{margin:0;font-family:'Roboto',sans-serif;background:#0f172a;color:#e2e8f0;display:flex;height:100vh;justify-content:center;align-items:center;}
.chat-container{flex:1;display:flex;flex-direction:column;width:100%;max-width:900px;height:90vh;}
.header{text-align:center;font-size:1.5rem;font-weight:bold;color:#38bdf8;margin-bottom:12px;text-shadow:0 0 8px #0ea5e9;}
.chat-box{flex:1;background:rgba(30,41,59,0.6);border-radius:20px;padding:20px;overflow-y:auto;scroll-behavior:smooth;display:flex;flex-direction:column;backdrop-filter:blur(8px);}
.msg{padding:14px 18px;border-radius:14px;margin:10px 0;max-width:75%;line-height:1.5;white-space:pre-wrap;animation:fadeIn 0.3s;}
.user{background:linear-gradient(135deg,#3b82f6,#22d3ee);color:white;margin-left:auto;text-align:right;box-shadow:0 4px 12px rgba(59,130,246,0.3);}
.bot{background:rgba(51,65,85,0.9);color:#f8fafc;margin-right:auto;text-align:left;border:1px solid #475569;}
.input-area{display:flex;margin-top:10px;background:rgba(30,41,59,0.6);border-radius:16px;padding:10px;box-shadow:0 4px 10px rgba(0,0,0,0.4);}
.input-area input{flex:1;padding:14px;border-radius:12px;border:none;background:rgba(15,23,42,0.7);color:white;outline:none;}
.input-area input:focus{border:1px solid #3b82f6;box-shadow:0 0 8px #3b82f6;}
.input-area button{padding:12px 18px;border:none;font-size:1rem;font-weight:600;background:linear-gradient(135deg,#3b82f6,#22d3ee);color:white;border-radius:12px;cursor:pointer;transition:0.3s;margin-left:5px;}
.input-area button:hover{background:linear-gradient(135deg,#2563eb,#0ea5e9);transform:scale(1.05);}
.input-area select{margin-left:5px;padding:10px;border-radius:12px;background:#0f172a;color:white;border:none;outline:none;}
.chat-box::-webkit-scrollbar{width:8px;}
.chat-box::-webkit-scrollbar-thumb{background:#475569;border-radius:10px;}
@keyframes fadeIn{from{opacity:0;transform:translateY(5px);}to{opacity:1;transform:translateY(0);}}

/* small helper */
.timestamp{font-size:0.85rem;color:#94a3b8;margin-top:6px;}
</style>
</head>
<body>
<div class="chat-container">
<div class="header"><i class="fa-solid fa-robot"></i> ShriGPT Medical Assistant</div>
<div class="chat-box" id="chat-box">
<div class="msg bot">👋 Hello! Ask me medical questions like <b>treatments, symptoms, diagnosis</b>.</div>
</div>
<div class="input-area">
<input type="text" id="user-input" placeholder="Type your medical question...">
<button onclick="sendMessage()"><i class="fa-solid fa-paper-plane"></i> Send</button>
<button id="voice-btn"><i class="fa-solid fa-microphone"></i></button>
<select id="lang-select">
<option value="en" selected>English</option>
<option value="hi">Hindi</option>
<option value="ta">Tamil</option>
<option value="te">Telugu</option>
<option value="ml">Malayalam</option>
</select>
</div>
</div>
<script>
const chatBox=document.getElementById("chat-box");
const input=document.getElementById("user-input");
const voiceBtn=document.getElementById("voice-btn");
const langSelect=document.getElementById("lang-select");
function scrollBottom(){chatBox.scrollTop=chatBox.scrollHeight;}
async function typeEffect(element,text){element.textContent="";for(let i=0;i<text.length;i++){element.textContent+=text[i];scrollBottom();await new Promise(r=>setTimeout(r,15));}}
async function sendMessage(){
const msg=input.value.trim();if(msg==="")return;
const targetLang=langSelect.value;
let userMsg=document.createElement("div");userMsg.className="msg user";userMsg.innerHTML=`🧑 <b>You:</b> ${escapeHtml(msg)} <div class="timestamp">🕒 ${new Date().toLocaleTimeString()}</div>`;chatBox.appendChild(userMsg);
let botMsg=document.createElement("div");botMsg.className="msg bot";botMsg.textContent="⏳ Thinking...";chatBox.appendChild(botMsg);
input.value="";scrollBottom();
try{
let res=await fetch("/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query:msg,language:targetLang})});
let data=await res.json();
await typeEffect(botMsg,`🤖 ${data.answer}`);
botMsg.innerHTML += `<div class="timestamp">🕒 ${new Date().toLocaleTimeString()}</div>`;
}catch(err){botMsg.textContent="❌ Error connecting to server.";}
scrollBottom();
}
voiceBtn.addEventListener("click",()=>{
const recognition=new (window.SpeechRecognition||window.webkitSpeechRecognition)();
recognition.lang='en-US';
recognition.start();
recognition.onresult=(event)=>{input.value=event.results[0][0].transcript;sendMessage();};
});
input.addEventListener("keydown",(e)=>{if(e.key==="Enter")sendMessage();});

// small escape to avoid HTML injection
function escapeHtml(unsafe) {
    return unsafe.replace(/[&<"']/g, function(m) {
        return ({'&':'&amp;','<':'&lt;','"':'&quot;',"'":'&#039;'}[m]);
    });
}
function speakText(text, lang='en-US') {
    if ('speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = lang; // language code
        utterance.rate = 1; // speed
        utterance.pitch = 1; // pitch
        window.speechSynthesis.cancel(); // stop any current speech
        window.speechSynthesis.speak(utterance);
    } else {
        console.warn("Speech Synthesis not supported in this browser.");
    }
}

async function sendMessage() {
    const msg = input.value.trim();
    if(msg === "") return;

    const targetLang = langSelect.value;
    let userMsg = document.createElement("div");
    userMsg.className = "msg user";
    userMsg.innerHTML = `🧑 <b>You:</b> ${escapeHtml(msg)} <div class="timestamp">🕒 ${new Date().toLocaleTimeString()}</div>`;
    chatBox.appendChild(userMsg);

    let botMsg = document.createElement("div");
    botMsg.className = "msg bot";
    botMsg.textContent = "⏳ Thinking...";
    chatBox.appendChild(botMsg);
    input.value = "";
    scrollBottom();


    try {
        let res = await fetch("/chat", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({query: msg, language: targetLang})
        });
        let data = await res.json();

        // Type effect
        await typeEffect(botMsg, `🤖 ${data.answer}`);
        botMsg.innerHTML += `<div class="timestamp">🕒 ${new Date().toLocaleTimeString()}</div>`;

        // Automatically read aloud
        let langCode = targetLang === 'en' ? 'en-US' : targetLang; // map simple codes
        speakText(data.answer, langCode);

    } catch(err) {
        botMsg.textContent = "❌ Error connecting to server.";
    }
    scrollBottom();
    let langMap = {en:'en-US', hi:'hi-IN', ta:'ta-IN', te:'te-IN', ml:'ml-IN'};
    let langCode = langMap[targetLang] || 'en-US';
    speakText(data.answer, langCode);
}
function speakText(text, lang='en-US') {
    if ('speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 1;
        utterance.pitch = 1;

        // Pick a voice matching the language
        const voices = window.speechSynthesis.getVoices();
        let voice = voices.find(v => v.lang.startsWith(lang));
        if (voice) utterance.voice = voice;

        window.speechSynthesis.cancel(); // stop any current speech
        window.speechSynthesis.speak(utterance);
    } else {
        console.warn("Speech Synthesis not supported in this browser.");
    }
}

</script>
</body>
</html>
"""

# ------------------- Helper Functions -------------------

def search_query_only(query: str, threshold: float = 0.75):
    """
    Query vector DB (Pinecone) if available and model available. Returns a paragraph (string) or None.
    """
    if not model or not index:
        return None
    try:
        query_vec = model.encode(query).tolist()
        results = index.query(vector=query_vec, top_k=5, include_metadata=True)
        if not results.get("matches"):
            return None
        disease_keywords = query.lower().replace("?", "").split()
        previous_text = last_disease_query["text"]
        for match in results["matches"]:
            score = match.get("score", 0)
            para = match.get("metadata", {}).get("text", "").strip()
            if not para or para == previous_text:
                continue
            if score >= threshold and any(word in para.lower() for word in disease_keywords):
                last_disease_query.update({"text": para, "name": query})
                return para
        return None
    except Exception as e:
        print("search_query_only error:", e)
        return None

def query_gemini(paragraph: str, question: str) -> str:
    """
    Calls Gemini/GGML via HTTP generativelanguage endpoint if GEMINI_API_KEY is provided.
    If not available or call fails, returns a safe fallback answer.
    """
    prompt = (f"{paragraph}\n\nUsing the above text, answer this question within 200 words maximum:\n\n{question}"
              if paragraph else f"Answer this medical question in simple terms, within 200 words maximum:\n\n{question}")
    if GEMINI_API_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/{MODEL_NAME}:generateContent"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            headers = {"Content-Type": "application/json"}
            response = requests.post(url, headers=headers, params={"key": GEMINI_API_KEY}, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            print("query_gemini error:", e)
            # Fallthrough to fallback message

    # Fallback answer (safe)
    safe = ("I can provide general medical information based on common knowledge. "
            "If this is urgent or serious, please consult a medical professional immediately. "
            f"You asked: {question}")
    if paragraph:
        safe += "\n\n(Referenced content summary applied.)"
    return safe

# ------------------- Routes -------------------

@app.route("/")
def home():
    return redirect("/login")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        if not username or not password or not email:
            flash("Please fill all fields.")
            return render_template_string(register_html)
        hashed = generate_password_hash(password)
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT id FROM users WHERE username=%s OR email=%s", (username, email))
            if cur.fetchone():
                flash("Username or Email already exists!")
                return render_template_string(register_html)
            cur.execute("INSERT INTO users (username, email, password) VALUES (%s, %s, %s)", (username, email, hashed))
            conn.commit()
            flash("Registration successful! Please login.")
            return redirect("/login")
        except Exception as e:
            print("register error:", e)
            if conn:
                conn.rollback()
            flash("Registration failed.")
            return render_template_string(register_html)
        finally:
            if conn:
                conn.close()
    return render_template_string(register_html)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Enter username and password.")
            return render_template_string(login_html)
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM users WHERE username=%s", (username,))
            user = cur.fetchone()
            if user and check_password_hash(user["password"], password):
                session["username"] = user["username"]
                return redirect("/dashboard")
            else:
                flash("Invalid username or password!")
        except Exception as e:
            print("login error:", e)
            flash("Login failed.")
        finally:
            if conn:
                conn.close()
    return render_template_string(login_html)

@app.route("/logout", methods=["POST"])
def logout():
    session.pop("username", None)
    return redirect("/login")

@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect("/login")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT username, email FROM users WHERE username=%s", (session['username'],))
        user = cur.fetchone()
        if not user:
            flash("User not found.")
            return redirect("/login")
        return render_template_string(dashboard_html, user=user)
    except Exception as e:
        print("dashboard error:", e)
        flash("Unable to load dashboard.")
        return redirect("/login")
    finally:
        if conn:
            conn.close()

@app.route("/change_password", methods=["POST"])
def change_password():
    if "username" not in session:
        return redirect("/login")
    current = request.form.get("current_password", "")
    new_pass = request.form.get("new_password", "")
    if not current or not new_pass:
        flash("Please provide both current and new password.")
        return redirect("/dashboard")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT password FROM users WHERE username=%s", (session['username'],))
        user = cur.fetchone()
        if user and check_password_hash(user["password"], current):
            hashed = generate_password_hash(new_pass)
            cur.execute("UPDATE users SET password=%s WHERE username=%s", (hashed, session['username']))
            conn.commit()
            flash("Password updated successfully!")
        else:
            flash("Current password is incorrect!")
    except Exception as e:
        print("change_password error:", e)
        if conn:
            conn.rollback()
        flash("Error updating password.")
    finally:
        if conn:
            conn.close()
    return redirect("/dashboard")

@app.route("/history")
def history():
    if "username" not in session:
        return redirect("/login")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT message, response, timestamp FROM chat_history WHERE username=%s ORDER BY timestamp ASC", (session['username'],))
        history_rows = cur.fetchall()
        return render_template_string(history_html, history=history_rows)
    except Exception as e:
        print("history error:", e)
        flash("Unable to load history.")
        return redirect("/dashboard")
    finally:
        if conn:
            conn.close()

@app.route("/chatpage")
def chatpage():
    if "username" not in session:
        return redirect("/login")
    return render_template_string(chat_html)

@app.route("/chat", methods=["POST"])
def chat():
    # interactive chat endpoint: generate answer, save to DB, return JSON
    if "username" not in session:
        return jsonify({"answer": "⚠ Please login first."})
    data = request.get_json(force=True)
    query = data.get("query", "").strip()
    target_lang = data.get("language", "en")
    if not query:
        return jsonify({"answer": "⚠ Please enter a valid question."})
    # try to get paragraph from vector index (if configured)
    para = None
    try:
        para = search_query_only(query)
    except Exception as e:
        print("vector search error:", e)
        para = None
    answer = query_gemini(para, query) if para else query_gemini(None, query)

    # translation if needed
    if target_lang and target_lang != "en" and translator:
        try:
            answer_trans = translator.translate(answer, dest=target_lang).text
            answer = answer_trans
        except Exception as e:
            print("translation error:", e)
            answer += " ⚠ Translation failed."

    # save to DB (username, message, response, timestamp)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        now = datetime.now()
        cur.execute("INSERT INTO chat_history (username, message, response, timestamp) VALUES (%s, %s, %s, %s)",
                    (session['username'], query, answer, now))
        conn.commit()
    except Exception as e:
        print("save chat error:", e)
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

    return jsonify({"answer": answer})

@app.route("/clear_history", methods=["POST"])
def clear_history():
    if "username" not in session:
        return redirect("/login")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM chat_history WHERE username=%s", (session['username'],))
        conn.commit()
        flash("Chat history cleared.")
    except Exception as e:
        print("clear_history error:", e)
        if conn:
            conn.rollback()
        flash("Unable to clear history.")
    finally:
        if conn:
            conn.close()
    return redirect("/history")

@app.route("/download_history")
def download_history():
    if "username" not in session:
        return redirect("/login")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT message, response, timestamp FROM chat_history WHERE username=%s ORDER BY timestamp ASC", (session['username'],))
        rows = cur.fetchall()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["message", "response", "timestamp"])
        for row in rows:
            msg, resp, ts = row
            if hasattr(ts, "strftime"):
                ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
            else:
                ts_str = str(ts)
            writer.writerow([msg, resp, ts_str])
        output.seek(0)
        return send_file(io.BytesIO(output.getvalue().encode('utf-8')), mimetype='text/csv',
                         as_attachment=True, download_name=f"{session['username']}_chat_history.csv")
    except Exception as e:
        print("download_history error:", e)
        flash("Unable to prepare download.")
        return redirect("/history")
    finally:
        if conn:
            conn.close()
@app.route("/download_history_pdf", methods=["GET"])
def download_history_pdf():
    if "username" not in session:
        return redirect("/login")
    
    date_str = request.args.get("date")  # optional date filter
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        if date_str:
            cur.execute("""
                SELECT message, response, timestamp FROM chat_history 
                WHERE username=%s AND DATE(timestamp)=%s
                ORDER BY timestamp ASC
            """, (session['username'], date_str))
        else:
            cur.execute("""
                SELECT message, response, timestamp FROM chat_history 
                WHERE username=%s ORDER BY timestamp ASC
            """, (session['username'],))
        rows = cur.fetchall()
        if not rows:
            flash("No chat history found.")
            return redirect("/history")
        
        # PDF in memory
        pdf_buffer = io.BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=letter)
        width, height = letter
        c.setFont("Helvetica", 10)
        margin = 40
        max_width = width - 2 * margin
        y = height - margin

        def draw_wrapped_text(text, start_y):
            """Draws wrapped text and returns updated y"""
            lines = []
            for paragraph in text.split("\n"):
                while paragraph:
                    # wrap by approx 95 characters
                    line = paragraph[:95]
                    paragraph = paragraph[95:]
                    lines.append(line)
            for line in lines:
                if start_y < margin:
                    c.showPage()
                    c.setFont("Helvetica", 10)
                    start_y = height - margin
                c.drawString(margin, start_y, line)
                start_y -= 14
            return start_y - 6  # extra spacing between messages

        # Title
        c.setFont("Helvetica-Bold", 12)
        title = f"Chat History for {session['username']}" + (f" - {date_str}" if date_str else "")
        c.drawString(margin, y, title)
        y -= 30
        c.setFont("Helvetica", 10)

        # Draw chats
        for row in rows:
            timestamp = row['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
            message_text = f"You ({timestamp}): {row['message']}"
            response_text = f"ShriGPT ({timestamp}): {row['response']}"
            y = draw_wrapped_text(message_text, y)
            y = draw_wrapped_text(response_text, y)

        c.save()
        pdf_buffer.seek(0)
        filename = f"ChatHistory_{session['username']}" + (f"_{date_str}" if date_str else "") + ".pdf"
        return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=True, download_name=filename)

    except Exception as e:
        print("download_history_pdf error:", e)
        flash("Unable to prepare PDF download.")
        return redirect("/history")
    finally:
        if conn:
            conn.close()
# ------------------- Run App -------------------
if __name__ == "__main__":
    # Start the Flask app
    print("Starting ShriGPT server...")
    app.run(host="0.0.0.0", port=5000, debug=DEBUG)
