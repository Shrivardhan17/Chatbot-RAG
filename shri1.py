from flask import Flask, request, jsonify, render_template_string, redirect, session, flash
import os
import requests
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone
from googletrans import Translator
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash

# ------------------- Load Environment Variables -------------------
load_dotenv()
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
INDEX_NAME = os.getenv("INDEX_NAME", "med-book")
MODEL_NAME = "models/gemini-2.0-flash"

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "chatbot_app")

# ------------------- Initialize Services -------------------
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(INDEX_NAME)
model = SentenceTransformer("all-MiniLM-L6-v2")
translator = Translator()

db = mysql.connector.connect(
    host=MYSQL_HOST,
    user=MYSQL_USER,
    password=MYSQL_PASSWORD,
    database=MYSQL_DB
)
cursor = db.cursor(dictionary=True)
last_disease_query = {"text": None, "name": None}

# ------------------- Flask App -------------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your_secret_key_here")

# ------------------- Templates -------------------

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

# -------- Register Page --------
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

# -------- Dashboard Page --------
dashboard_html = """... (same as your original dashboard_html code) ..."""

# -------- Chat Page with Voice Output --------
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
/* (same styling as before) */
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

// Scroll bottom helper
function scrollBottom(){chatBox.scrollTop=chatBox.scrollHeight;}

// Typewriter effect
async function typeEffect(element,text){
    element.textContent="";
    for(let i=0;i<text.length;i++){
        element.textContent+=text[i];
        scrollBottom();
        await new Promise(r=>setTimeout(r,15));
    }
}

// Speak text aloud (Text-to-Speech)
function speakText(text, lang){
    if(!('speechSynthesis' in window)) return;
    const utter = new SpeechSynthesisUtterance(text);
    switch(lang){
        case 'hi': utter.lang='hi-IN'; break;
        case 'ta': utter.lang='ta-IN'; break;
        case 'te': utter.lang='te-IN'; break;
        case 'ml': utter.lang='ml-IN'; break;
        default: utter.lang='en-US';
    }
    utter.pitch=1; utter.rate=1; utter.volume=1;
    window.speechSynthesis.cancel(); // stop previous
    window.speechSynthesis.speak(utter);
}

// Send message to server
async function sendMessage(){
    const msg=input.value.trim();
    if(msg==="")return;
    const targetLang=langSelect.value;

    // Display user message
    let userMsg=document.createElement("div");
    userMsg.className="msg user";
    userMsg.textContent=msg;
    chatBox.appendChild(userMsg);

    // Placeholder bot message
    let botMsg=document.createElement("div");
    botMsg.className="msg bot";
    botMsg.textContent="⏳ Thinking...";
    chatBox.appendChild(botMsg);

    input.value="";
    scrollBottom();

    try{
        let res=await fetch("/chat",{
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body:JSON.stringify({query:msg,language:targetLang})
        });
        let data=await res.json();
        await typeEffect(botMsg,data.answer);
        speakText(data.answer, targetLang); // 🔊 Read answer aloud
    }catch(err){
        botMsg.textContent="❌ Error connecting to server.";
    }
    scrollBottom();
}

// Voice recognition
voiceBtn.addEventListener("click",()=>{
    const recognition=new (window.SpeechRecognition||window.webkitSpeechRecognition)();
    recognition.lang='en-US';
    recognition.start();
    recognition.onresult=(event)=>{
        input.value=event.results[0][0].transcript;
        sendMessage();
    };
});
input.addEventListener("keydown",(e)=>{if(e.key==="Enter")sendMessage();});
</script>
</body>
</html>
"""

# ------------------- Helper Functions -------------------
def search_query_only(query: str, threshold: float = 0.75):
    query_vec = model.encode(query).tolist()
    results = index.query(vector=query_vec, top_k=5, include_metadata=True)
    if not results.get("matches"):
        return None
    disease_keywords = query.lower().replace("?","").split()
    previous_text = last_disease_query["text"]
    for match in results["matches"]:
        score = match.get("score",0)
        para = match["metadata"].get("text","").strip()
        if not para or para==previous_text:
            continue
        if score>=threshold and any(word in para.lower() for word in disease_keywords):
            last_disease_query.update({"text":para,"name":query})
            return para
    return None

def query_gemini(paragraph: str, question: str) -> str:
    prompt = (f"{paragraph}\n\nUsing the above text, answer this question within 200 words maximum:\n\n{question}" 
              if paragraph else f"Answer this medical question in simple terms, within 200 words maximum:\n\n{question}")
    url = f"https://generativelanguage.googleapis.com/v1beta/{MODEL_NAME}:generateContent"
    payload = {"contents":[{"parts":[{"text":prompt}]}]}
    headers = {"Content-Type":"application/json"}
    try:
        response = requests.post(url, headers=headers, params={"key":GEMINI_API_KEY}, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except:
        return "⚠ Unable to get answer from Gemini."

# ------------------- Routes -------------------
@app.route("/")
def home():
    return redirect("/login")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        hashed = generate_password_hash(password)
        cursor.execute("SELECT * FROM users WHERE username=%s OR email=%s",(username,email))
        if cursor.fetchone():
            flash("Username or Email already exists!")
            return render_template_string(register_html)
        cursor.execute("INSERT INTO users (username,email,password) VALUES (%s,%s,%s)",(username,email,hashed))
        db.commit()
        flash("Registration successful! Please login.")
        return redirect("/login")
    return render_template_string(register_html)

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        username = request.form["username"]
        password = request.form["password"]
        cursor.execute("SELECT * FROM users WHERE username=%s",(username,))
        user = cursor.fetchone()
        if user and check_password_hash(user["password"],password):
            session["username"] = user["username"]
            return redirect("/dashboard")
        else:
            flash("Invalid username or password!")
    return render_template_string(login_html)

@app.route("/logout", methods=["POST"])
def logout():
    session.pop("username",None)
    return redirect("/login")

@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect("/login")
    cursor.execute("SELECT username,email FROM users WHERE username=%s",(session['username'],))
    user = cursor.fetchone()
    return render_template_string(dashboard_html,user=user)

@app.route("/chatpage")
def chatpage():
    if "username" not in session:
        return redirect("/login")
    return render_template_string(chat_html)

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        query = data.get("query", "")
        target_lang = data.get("language", "en")

        if not query:
            return jsonify({"answer": "❌ Please enter a valid question."})

        # Step 1: Search Pinecone for related text
        paragraph = search_query_only(query)

        # Step 2: Get simplified answer from Gemini
        answer = query_gemini(paragraph, query)

        # Step 3: Translate to target language
        if target_lang != "en":
            try:
                answer = translator.translate(answer, dest=target_lang).text
            except:
                answer += "\n\n⚠ Translation failed. Showing English answer."

        return jsonify({"answer": answer})
    except Exception as e:
        print("Chat Error:", e)
        return jsonify({"answer": "⚠ An internal error occurred. Please try again."})

# ------------------- Main -------------------
if __name__ == "__main__":
    # Create table if not exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            email VARCHAR(150) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.commit()

    print("🚀 ShriGPT Medical Assistant is running on http://127.0.0.1:5000")
    app.run(debug=True)
