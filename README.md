# 🚀 Devetryx

Devetryx is an AI-powered web-based coding platform designed for beginners, students, and developers. It supports multiple programming, scripting, and markup languages with an integrated compiler, debugger, and intelligent learning assistant.

---

## 🌟 Features

- 🧠 AI-Powered Learning Mode (Code Analysis & Feedback)
- 💻 Real-Time Compiler Mode
- 📊 Skill Scoring & Performance Insights
- 🛠 Secure Python Code Execution (Sandboxed)
- 📁 Multi-File Support
- 🔐 AST-Based Security Filtering
- ⚡ Django + Channels + Daphne Powered
- 🌐 Web-Based Interactive Terminal
- 📚 Beginner-Friendly + Developer-Oriented

---

## 🏗️ Built With

- **Backend:** Django 5
- **Async Engine:** Django Channels
- **ASGI Server:** Daphne
- **Frontend:** HTML, CSS, JavaScript
- **Editor:** Monaco Editor
- **Security:** AST-based import filtering & resource limiting

---

## 🧠 Modes

### 🖥 Compiler Mode
Runs code like a normal terminal and displays raw output.

### 🧠 Learning Mode
Analyzes your code and provides:
- Skill Score
- Level Detection
- Improvement Roadmap
- Smart Feedback
- Clean Program Output

---

## 🔒 Security Architecture

- Import whitelisting
- Unsafe module blocking
- Unsafe function detection
- Resource limits (CPU & Memory)
- Execution timeout protection
- Temporary isolated workspace

---

## 📦 Installation
```bash
1️⃣ Clone Repository
git clone https://github.com/your-username/devetryx.git
cd devetryx

2️⃣ Create Virtual Environment
python -m venv venv
source venv/bin/activate   # Linux / Mac
venv\Scripts\activate      # Windows

3️⃣ Install Requirements
pip install -r requirements.txt

4️⃣ Run Migrations
python manage.py migrate

5️⃣ Start Server
python manage.py runserver
