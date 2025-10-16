import os
import io
import csv
import random
import sqlite3
from datetime import datetime, timedelta
from string import Template
from typing import List, Optional

from fastapi import FastAPI, Form, UploadFile, File, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# --- Database Setup ---
DB_PATH = os.environ.get("DB_PATH", "autodate.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            subscription_status TEXT DEFAULT 'inactive',
            subscription_end_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Add can_use_retrofit_tool column if it doesn't exist
    def _column_exists(cursor, table, column):
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cursor.fetchall()]
        return column in columns
    
    if not _column_exists(cur, "users", "can_use_retrofit_tool"):
        cur.execute("ALTER TABLE users ADD COLUMN can_use_retrofit_tool INTEGER NOT NULL DEFAULT 1")
    
    conn.commit()
    conn.close()

init_db()

app = FastAPI()

# Admin email - set via environment variable
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").lower()

# --- Cookie & Auth Helpers ---
SECRET = os.environ.get("SECRET", "change-me-in-production")

def set_cookie(resp: RedirectResponse, key: str, val: str):
    resp.set_cookie(key, val, httponly=True, max_age=30*24*60*60)

def get_cookie(request: Request, key: str) -> str:
    return request.cookies.get(key, "")

def get_user_row_by_email(email: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email=?", (email.lower(),))
    row = cur.fetchone()
    conn.close()
    return row

def require_active_user_row(request: Request):
    email = get_cookie(request, "user_email")
    if not email:
        return RedirectResponse("/login", status_code=302)
    
    row = get_user_row_by_email(email)
    if not row:
        return RedirectResponse("/login", status_code=302)
    
    # Check subscription
    status = row["subscription_status"]
    if status != "active":
        return HTMLResponse("<h1>Subscription Inactive</h1><p>Please subscribe or contact support.</p>")
    
    # Safe access to subscription_end_date
    try:
        end = row["subscription_end_date"]
    except (KeyError, TypeError):
        end = None
    
    if end:
        try:
            end_dt = datetime.fromisoformat(end)
            if datetime.now() > end_dt:
                return HTMLResponse("<h1>Subscription Expired</h1><p>Please renew your subscription.</p>")
        except:
            pass
    
    return row

def require_admin(request: Request):
    row = require_active_user_row(request)
    if isinstance(row, (RedirectResponse, HTMLResponse)):
        return row
    
    if not ADMIN_EMAIL or row["email"].lower() != ADMIN_EMAIL:
        return HTMLResponse("<h1>Unauthorized</h1><p>Admin access only</p>", status_code=403)
    
    return row

# --- HTML Templates ---
login_html = Template("""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - AutoDate</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            background: white;
            padding: 2rem;
            border-radius: 1rem;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            width: 90%;
            max-width: 400px;
        }
        h1 { color: #667eea; margin-bottom: 1.5rem; text-align: center; }
        .form-group { margin-bottom: 1rem; }
        label { display: block; margin-bottom: 0.5rem; color: #333; font-weight: 500; }
        input {
            width: 100%;
            padding: 0.75rem;
            border: 2px solid #e0e0e0;
            border-radius: 0.5rem;
            font-size: 1rem;
        }
        input:focus { outline: none; border-color: #667eea; }
        button {
            width: 100%;
            padding: 0.75rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 0.5rem;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            margin-top: 1rem;
        }
        button:hover { opacity: 0.9; }
        .error { color: #e53e3e; margin-bottom: 1rem; padding: 0.75rem; background: #fff5f5; border-radius: 0.5rem; }
        .link { text-align: center; margin-top: 1rem; }
        .link a { color: #667eea; text-decoration: none; }
        .link a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 AutoDate Login</h1>
        $error_msg
        <form method="POST" action="/login">
            <div class="form-group">
                <label>Email</label>
                <input type="email" name="email" required>
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit">Login</button>
        </form>
        <div class="link">
            <a href="/signup">Don't have an account? Sign up</a>
        </div>
    </div>
</body>
</html>
""")

signup_html = Template("""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign Up - AutoDate</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            background: white;
            padding: 2rem;
            border-radius: 1rem;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            width: 90%;
            max-width: 400px;
        }
        h1 { color: #667eea; margin-bottom: 1.5rem; text-align: center; }
        .form-group { margin-bottom: 1rem; }
        label { display: block; margin-bottom: 0.5rem; color: #333; font-weight: 500; }
        input {
            width: 100%;
            padding: 0.75rem;
            border: 2px solid #e0e0e0;
            border-radius: 0.5rem;
            font-size: 1rem;
        }
        input:focus { outline: none; border-color: #667eea; }
        button {
            width: 100%;
            padding: 0.75rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 0.5rem;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            margin-top: 1rem;
        }
        button:hover { opacity: 0.9; }
        .error { color: #e53e3e; margin-bottom: 1rem; padding: 0.75rem; background: #fff5f5; border-radius: 0.5rem; }
        .link { text-align: center; margin-top: 1rem; }
        .link a { color: #667eea; text-decoration: none; }
        .link a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 Create Account</h1>
        $error_msg
        <form method="POST" action="/signup">
            <div class="form-group">
                <label>Email</label>
                <input type="email" name="email" required>
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit">Sign Up</button>
        </form>
        <div class="link">
            <a href="/login">Already have an account? Login</a>
        </div>
    </div>
</body>
</html>
""")

tool2_html = Template("""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Timestamp Tool - AutoDate</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 2rem;
        }
        .header {
            text-align: center;
            color: white;
            margin-bottom: 2rem;
        }
        .header h1 { margin-bottom: 0.5rem; }
        .nav {
            text-align: center;
            margin-bottom: 2rem;
        }
        .nav a {
            color: white;
            text-decoration: none;
            margin: 0 1rem;
            font-weight: 500;
        }
        .nav a:hover { text-decoration: underline; }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            padding: 2rem;
            border-radius: 1rem;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        .form-group { margin-bottom: 1.5rem; }
        label { display: block; margin-bottom: 0.5rem; color: #333; font-weight: 500; }
        input, select {
            width: 100%;
            padding: 0.75rem;
            border: 2px solid #e0e0e0;
            border-radius: 0.5rem;
            font-size: 1rem;
        }
        input:focus, select:focus { outline: none; border-color: #667eea; }
        button {
            width: 100%;
            padding: 0.75rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 0.5rem;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
        }
        button:hover { opacity: 0.9; }
        .result {
            margin-top: 2rem;
            padding: 1rem;
            background: #f7fafc;
            border-radius: 0.5rem;
            border: 2px solid #667eea;
        }
        .result img { max-width: 100%; height: auto; border-radius: 0.5rem; }
    </style>
</head>
<body>
    <div class="header">
        <h1>⏰ Timestamp Tool</h1>
    </div>
    <div class="nav">
        $admin_link
        <a href="/billing">Billing</a>
        <a href="/logout">Logout</a>
    </div>
    <div class="container">
        <form id="stampForm" enctype="multipart/form-data">
            <div class="form-group">
                <label>Upload Image</label>
                <input type="file" name="image" accept="image/*" required>
            </div>
            <div class="form-group">
                <label>Date Format</label>
                <select name="date_format">
                    <option value="dd_slash_mm_yyyy">DD/MM/YYYY</option>
                    <option value="mm_slash_dd_yyyy">MM/DD/YYYY</option>
                    <option value="yyyy_dash_mm_dd">YYYY-MM-DD</option>
                </select>
            </div>
            <div class="form-group">
                <label>Time Format</label>
                <select name="time_format">
                    <option value="24h">24 Hour (HH:MM:SS)</option>
                    <option value="12h">12 Hour (HH:MM:SS AM/PM)</option>
                </select>
            </div>
            <div class="form-group">
                <label>Font Size</label>
                <input type="number" name="font_size" value="40" min="10" max="200">
            </div>
            <div class="form-group">
                <label>Text Color (Hex)</label>
                <input type="text" name="color" value="#FFFFFF" pattern="^#[0-9A-Fa-f]{6}$">
            </div>
            <button type="submit">Generate Timestamp</button>
        </form>
        <div id="result" class="result" style="display:none;">
            <h3>Result:</h3>
            <img id="resultImg" src="" alt="Timestamped Image">
            <br><br>
            <a id="downloadLink" href="" download="timestamped.jpg">
                <button type="button">Download Image</button>
            </a>
        </div>
    </div>
    <script>
        document.getElementById('stampForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            
            try {
                const response = await fetch('/api/stamp', {
                    method: 'POST',
                    body: formData
                });
                
                if (response.ok) {
                    const blob = await response.blob();
                    const url = URL.createObjectURL(blob);
                    
                    document.getElementById('resultImg').src = url;
                    document.getElementById('downloadLink').href = url;
                    document.getElementById('result').style.display = 'block';
                } else {
                    alert('Error generating timestamp');
                }
            } catch (error) {
                alert('Error: ' + error.message);
            }
        });
    </script>
</body>
</html>
""")

# --- Routes ---
@app.get("/")
def root():
    return RedirectResponse("/tool2")

@app.get("/__whoami")
def whoami():
    return {"status": "main.py active", "timestamp": datetime.now().isoformat()}

@app.get("/login", response_class=HTMLResponse)
def login_page(error: str = ""):
    error_msg = f'<div class="error">{error}</div>' if error else ""
    return HTMLResponse(login_html.safe_substitute(error_msg=error_msg))

@app.post("/login")
def login_post(email: str = Form(...), password: str = Form(...)):
    row = get_user_row_by_email(email)
    if not row or row["password"] != password:
        return RedirectResponse("/login?error=Invalid credentials", status_code=302)
    
    resp = RedirectResponse("/tool2", status_code=302)
    set_cookie(resp, "user_email", email.lower())
    return resp

@app.get("/signup", response_class=HTMLResponse)
def signup_page(error: str = ""):
    error_msg = f'<div class="error">{error}</div>' if error else ""
    return HTMLResponse(signup_html.safe_substitute(error_msg=error_msg))

@app.post("/signup")
def signup_post(email: str = Form(...), password: str = Form(...)):
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute(
            "INSERT INTO users (email, password, subscription_status) VALUES (?, ?, ?)",
            (email.lower(), password, "active")
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return RedirectResponse("/signup?error=Email already exists", status_code=302)
    finally:
        conn.close()
    
    resp = RedirectResponse("/tool2", status_code=302)
    set_cookie(resp, "user_email", email.lower())
    return resp

@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("user_email")
    return resp

@app.get("/tool2", response_class=HTMLResponse)
def tool2(request: Request):
    row = require_active_user_row(request)
    if isinstance(row, (RedirectResponse, HTMLResponse)):
        return row
    
    show_admin = ADMIN_EMAIL and row["email"].lower() == ADMIN_EMAIL
    
    # Simple version - show to everyone
    admin_link = ""
    if show_admin:
        admin_link = '<a href="/admin">Admin</a> '
    
    # Always show Retrofit Design link for now
    admin_link += '<a href="/retrofit-tool" style="color:#22c55e;font-weight:600">🏠 Retrofit Design</a> '
    
    return HTMLResponse(tool2_html.safe_substitute(admin_link=admin_link))

# --- NEW: Native Retrofit Design Tool ---
@app.get("/retrofit-tool", response_class=HTMLResponse)
def retrofit_tool(request: Request):
    row = require_active_user_row(request)
    if isinstance(row, (RedirectResponse, HTMLResponse)):
        return row
    
    html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Retrofit Design Tool - AutoDate</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            min-height: 100vh;
            padding: 2rem;
        }
        
        .header {
            text-align: center;
            color: white;
            margin-bottom: 2rem;
        }
        
        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }
        
        .nav {
            text-align: center;
            margin-bottom: 2rem;
        }
        
        .nav a {
            color: white;
            text-decoration: none;
            margin: 0 1rem;
            font-weight: 500;
            transition: all 0.3s;
        }
        
        .nav a:hover {
            text-decoration: underline;
            color: #22c55e;
        }
        
        .container {
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 1.5rem;
            box-shadow: 0 25px 80px rgba(0,0,0,0.4);
            overflow: hidden;
        }
        
        .progress-bar {
            display: flex;
            background: #f8fafc;
            padding: 1.5rem 2rem;
            border-bottom: 2px solid #e2e8f0;
        }
        
        .progress-step {
            flex: 1;
            text-align: center;
            position: relative;
        }
        
        .progress-step::after {
            content: '';
            position: absolute;
            top: 15px;
            left: 50%;
            width: 100%;
            height: 3px;
            background: #e2e8f0;
            z-index: 0;
        }
        
        .progress-step:last-child::after {
            display: none;
        }
        
        .progress-circle {
            width: 40px;
            height: 40px;
            background: white;
            border: 3px solid #e2e8f0;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 0.5rem;
            font-weight: bold;
            color: #94a3b8;
            position: relative;
            z-index: 1;
        }
        
        .progress-step.active .progress-circle {
            background: #22c55e;
            border-color: #22c55e;
            color: white;
        }
        
        .progress-step.completed .progress-circle {
            background: #3b82f6;
            border-color: #3b82f6;
            color: white;
        }
        
        .progress-label {
            font-size: 0.85rem;
            color: #64748b;
            font-weight: 500;
        }
        
        .content {
            padding: 3rem;
        }
        
        .step-title {
            font-size: 2rem;
            color: #1e293b;
            margin-bottom: 0.5rem;
            font-weight: 700;
        }
        
        .step-subtitle {
            color: #64748b;
            margin-bottom: 2rem;
            font-size: 1.1rem;
        }
        
        .format-tabs {
            display: flex;
            gap: 1rem;
            margin-bottom: 2rem;
        }
        
        .format-tab {
            flex: 1;
            padding: 1.5rem;
            background: #f8fafc;
            border: 3px solid #e2e8f0;
            border-radius: 1rem;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .format-tab:hover {
            border-color: #22c55e;
            background: #f0fdf4;
        }
        
        .format-tab.active {
            border-color: #22c55e;
            background: #f0fdf4;
        }
        
        .format-tab h3 {
            color: #1e293b;
            margin-bottom: 0.5rem;
            font-size: 1.3rem;
        }
        
        .format-tab p {
            color: #64748b;
            font-size: 0.9rem;
        }
        
        .upload-section {
            margin-bottom: 2rem;
        }
        
        .upload-label {
            display: block;
            font-weight: 600;
            color: #1e293b;
            margin-bottom: 0.75rem;
            font-size: 1.1rem;
        }
        
        .upload-zone {
            border: 3px dashed #cbd5e1;
            border-radius: 1rem;
            padding: 3rem;
            text-align: center;
            background: #f8fafc;
            cursor: pointer;
            transition: all 0.3s;
            position: relative;
        }
        
        .upload-zone:hover {
            border-color: #22c55e;
            background: #f0fdf4;
        }
        
        .upload-zone.dragover {
            border-color: #22c55e;
            background: #dcfce7;
        }
        
        .upload-icon {
            font-size: 3rem;
            margin-bottom: 1rem;
            color: #3b82f6;
        }
        
        .upload-text {
            font-size: 1.1rem;
            color: #1e293b;
            margin-bottom: 0.5rem;
            font-weight: 500;
        }
        
        .upload-hint {
            color: #64748b;
            font-size: 0.9rem;
        }
        
        .file-input {
            display: none;
        }
        
        .file-display {
            display: flex;
            align-items: center;
            padding: 1rem;
            background: #f0fdf4;
            border: 2px solid #22c55e;
            border-radius: 0.75rem;
            margin-top: 1rem;
        }
        
        .file-icon {
            width: 40px;
            height: 40px;
            background: #22c55e;
            color: white;
            border-radius: 0.5rem;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            margin-right: 1rem;
        }
        
        .file-info {
            flex: 1;
        }
        
        .file-name {
            font-weight: 600;
            color: #1e293b;
            margin-bottom: 0.25rem;
        }
        
        .file-size {
            color: #64748b;
            font-size: 0.9rem;
        }
        
        .file-remove {
            color: #ef4444;
            cursor: pointer;
            font-size: 1.5rem;
            padding: 0.5rem;
        }
        
        .file-remove:hover {
            color: #dc2626;
        }
        
        .button-group {
            display: flex;
            gap: 1rem;
            margin-top: 2rem;
        }
        
        .btn {
            flex: 1;
            padding: 1rem;
            border: none;
            border-radius: 0.75rem;
            font-size: 1.1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .btn-back {
            background: #f1f5f9;
            color: #475569;
        }
        
        .btn-back:hover {
            background: #e2e8f0;
        }
        
        .btn-continue {
            background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
            color: white;
        }
        
        .btn-continue:hover {
            opacity: 0.9;
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(34, 197, 94, 0.3);
        }
        
        .btn-continue:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }
        
        .processing {
            display: none;
            padding: 2rem;
            background: #f8fafc;
            border-radius: 1rem;
            text-align: center;
            margin-top: 2rem;
        }
        
        .processing.active {
            display: block;
        }
        
        .spinner {
            width: 60px;
            height: 60px;
            border: 5px solid #e2e8f0;
            border-top-color: #22c55e;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 1rem;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .processing-text {
            font-size: 1.1rem;
            color: #1e293b;
            font-weight: 600;
        }
        
        .hidden {
            display: none !important;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🏠 AutoDate - Retrofit Design</h1>
    </div>
    
    <div class="nav">
        <a href="/admin">Admin</a>
        <a href="/tool2">Timestamp Tool</a>
        <a href="/billing">Billing</a>
        <a href="/logout">Logout</a>
    </div>
    
    <div class="container">
        <div class="progress-bar">
            <div class="progress-step active">
                <div class="progress-circle">1</div>
                <div class="progress-label">Upload Documents</div>
            </div>
            <div class="progress-step">
                <div class="progress-circle">2</div>
                <div class="progress-label">Select Measures</div>
            </div>
            <div class="progress-step">
                <div class="progress-circle">3</div>
                <div class="progress-label">Answer Questions</div>
            </div>
            <div class="progress-step">
                <div class="progress-circle">4</div>
                <div class="progress-label">Upload Calcs</div>
            </div>
            <div class="progress-step">
                <div class="progress-circle">5</div>
                <div class="progress-label">Generate Design</div>
            </div>
        </div>
        
        <div class="content">
            <h2 class="step-title">Step 1: Upload Site Notes</h2>
            <p class="step-subtitle">Choose your format and upload the required documents</p>
            
            <div class="format-tabs">
                <div class="format-tab active" id="pashub-tab" onclick="selectFormat('pashub')">
                    <h3>📋 PAS Hub Format</h3>
                    <p>Upload site notes + condition report</p>
                </div>
                <div class="format-tab" id="elmhurst-tab" onclick="selectFormat('elmhurst')">
                    <h3>📊 Elmhurst Format</h3>
                    <p>Upload site notes + condition report</p>
                </div>
            </div>
            
            <!-- PAS Hub Uploads -->
            <div id="pashub-uploads">
                <div class="upload-section">
                    <label class="upload-label">1. PAS Hub Site Notes PDF</label>
                    <div class="upload-zone" id="pashub-sitenotes-zone" onclick="document.getElementById('pashub-sitenotes-input').click()">
                        <div class="upload-icon">📄</div>
                        <div class="upload-text">Drop PAS Hub Site Notes Here</div>
                        <div class="upload-hint">or click to browse for PDF file</div>
                    </div>
                    <input type="file" id="pashub-sitenotes-input" class="file-input" accept=".pdf" onchange="handleFileSelect(event, 'pashub-sitenotes')">
                    <div id="pashub-sitenotes-display" class="hidden"></div>
                </div>
                
                <div class="upload-section">
                    <label class="upload-label">2. PAS Hub Condition Report PDF (with photos)</label>
                    <div class="upload-zone" id="pashub-condition-zone" onclick="document.getElementById('pashub-condition-input').click()">
                        <div class="upload-icon">📷</div>
                        <div class="upload-text">Drop Condition Report Here</div>
                        <div class="upload-hint">or click to browse for PDF file</div>
                    </div>
                    <input type="file" id="pashub-condition-input" class="file-input" accept=".pdf" onchange="handleFileSelect(event, 'pashub-condition')">
                    <div id="pashub-condition-display" class="hidden"></div>
                </div>
            </div>
            
            <!-- Elmhurst Uploads -->
            <div id="elmhurst-uploads" class="hidden">
                <div class="upload-section">
                    <label class="upload-label">1. Elmhurst Site Notes PDF (RdSAP Assessment)</label>
                    <div class="upload-zone" id="elmhurst-sitenotes-zone" onclick="document.getElementById('elmhurst-sitenotes-input').click()">
                        <div class="upload-icon">📄</div>
                        <div class="upload-text">Drop Elmhurst Site Notes Here</div>
                        <div class="upload-hint">or click to browse for PDF file</div>
                    </div>
                    <input type="file" id="elmhurst-sitenotes-input" class="file-input" accept=".pdf" onchange="handleFileSelect(event, 'elmhurst-sitenotes')">
                    <div id="elmhurst-sitenotes-display" class="hidden"></div>
                </div>
                
                <div class="upload-section">
                    <label class="upload-label">2. Elmhurst Condition Report PDF (with photos)</label>
                    <div class="upload-zone" id="elmhurst-condition-zone" onclick="document.getElementById('elmhurst-condition-input').click()">
                        <div class="upload-icon">📷</div>
                        <div class="upload-text">Drop Condition Report Here</div>
                        <div class="upload-hint">or click to browse for PDF file</div>
                    </div>
                    <input type="file" id="elmhurst-condition-input" class="file-input" accept=".pdf" onchange="handleFileSelect(event, 'elmhurst-condition')">
                    <div id="elmhurst-condition-display" class="hidden"></div>
                </div>
            </div>
            
            <div class="processing" id="processing">
                <div class="spinner"></div>
                <div class="processing-text">Processing documents and moving to Step 2... (Full processing coming next!)</div>
            </div>
            
            <div class="button-group">
                <button class="btn btn-back" onclick="window.location.href='/tool2'">Back</button>
                <button class="btn btn-continue" id="continue-btn" onclick="continueToStep2()" disabled>Continue to Measure Selection</button>
            </div>
        </div>
    </div>
    
    <script>
        let currentFormat = 'pashub';
        let uploadedFiles = {
            'pashub-sitenotes': null,
            'pashub-condition': null,
            'elmhurst-sitenotes': null,
            'elmhurst-condition': null
        };
        
        function selectFormat(format) {
            currentFormat = format;
            
            // Update tabs
            document.getElementById('pashub-tab').classList.toggle('active', format === 'pashub');
            document.getElementById('elmhurst-tab').classList.toggle('active', format === 'elmhurst');
            
            // Show/hide upload sections
            document.getElementById('pashub-uploads').classList.toggle('hidden', format !== 'pashub');
            document.getElementById('elmhurst-uploads').classList.toggle('hidden', format !== 'elmhurst');
            
            updateContinueButton();
        }
        
        function handleFileSelect(event, uploadType) {
            const file = event.target.files[0];
            if (!file) return;
            
            uploadedFiles[uploadType] = file;
            
            // Create file display
            const displayDiv = document.getElementById(uploadType + '-display');
            displayDiv.className = 'file-display';
            displayDiv.innerHTML = `
                <div class="file-icon">PDF</div>
                <div class="file-info">
                    <div class="file-name">${file.name}</div>
                    <div class="file-size">${(file.size / 1024 / 1024).toFixed(2)} MB</div>
                </div>
                <div class="file-remove" onclick="removeFile('${uploadType}')">×</div>
            `;
            
            updateContinueButton();
        }
        
        function removeFile(uploadType) {
            uploadedFiles[uploadType] = null;
            document.getElementById(uploadType + '-display').className = 'hidden';
            document.getElementById(uploadType + '-input').value = '';
            updateContinueButton();
        }
        
        function updateContinueButton() {
            const btn = document.getElementById('continue-btn');
            
            if (currentFormat === 'pashub') {
                btn.disabled = !(uploadedFiles['pashub-sitenotes'] && uploadedFiles['pashub-condition']);
            } else {
                btn.disabled = !(uploadedFiles['elmhurst-sitenotes'] && uploadedFiles['elmhurst-condition']);
            }
        }
        
        async function continueToStep2() {
            // Show processing
            document.getElementById('processing').classList.add('active');
            document.getElementById('continue-btn').disabled = true;
            
            // Prepare FormData
            const formData = new FormData();
            formData.append('format', currentFormat);
            
            if (currentFormat === 'pashub') {
                formData.append('sitenotes', uploadedFiles['pashub-sitenotes']);
                formData.append('condition', uploadedFiles['pashub-condition']);
            } else {
                formData.append('sitenotes', uploadedFiles['elmhurst-sitenotes']);
                formData.append('condition', uploadedFiles['elmhurst-condition']);
            }
            
            try {
                const response = await fetch('/api/retrofit/process-upload', {
                    method: 'POST',
                    body: formData
                });
                
                if (response.ok) {
                    const result = await response.json();
                    
                    // Simulate processing delay (remove this later when real processing is added)
                    setTimeout(() => {
                        alert('Upload successful! Moving to Step 2: Measure Selection (Coming next!)');
                        // TODO: Navigate to Step 2
                    }, 2000);
                } else {
                    alert('Error processing documents');
                    document.getElementById('processing').classList.remove('active');
                    updateContinueButton();
                }
            } catch (error) {
                alert('Error: ' + error.message);
                document.getElementById('processing').classList.remove('active');
                updateContinueButton();
            }
        }
        
        // Drag and drop handlers
        ['pashub-sitenotes', 'pashub-condition', 'elmhurst-sitenotes', 'elmhurst-condition'].forEach(type => {
            const zone = document.getElementById(type + '-zone');
            
            zone.addEventListener('dragover', (e) => {
                e.preventDefault();
                zone.classList.add('dragover');
            });
            
            zone.addEventListener('dragleave', () => {
                zone.classList.remove('dragover');
            });
            
            zone.addEventListener('drop', (e) => {
                e.preventDefault();
                zone.classList.remove('dragover');
                
                const file = e.dataTransfer.files[0];
                if (file && file.type === 'application/pdf') {
                    const input = document.getElementById(type + '-input');
                    const dataTransfer = new DataTransfer();
                    dataTransfer.items.add(file);
                    input.files = dataTransfer.files;
                    
                    input.dispatchEvent(new Event('change'));
                }
            });
        });
    </script>
</body>
</html>
    """
    
    return HTMLResponse(html)

# --- NEW: Retrofit Upload Processing API ---
@app.post("/api/retrofit/process-upload")
async def process_retrofit_upload(
    format: str = Form(...),
    sitenotes: UploadFile = File(...),
    condition: UploadFile = File(...)
):
    """
    Process uploaded site notes and condition report.
    This is a placeholder - full PDF processing will be added next.
    """
    
    # TODO: Add PDF processing here using PyPDF2
    # TODO: Extract data from site notes based on format
    # TODO: Store extracted data for Step 2
    
    return JSONResponse({
        "success": True,
        "format": format,
        "sitenotes_filename": sitenotes.filename,
        "condition_filename": condition.filename,
        "message": "Documents uploaded successfully. Ready for Step 2!"
    })

# --- Image Stamping API ---
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

@app.post("/api/stamp")
async def stamp_image(
    image: UploadFile = File(...),
    date_format: str = Form("dd_slash_mm_yyyy"),
    time_format: str = Form("24h"),
    font_size: int = Form(40),
    color: str = Form("#FFFFFF")
):
    # Read image
    img_bytes = await image.read()
    img = Image.open(BytesIO(img_bytes))
    
    # Get EXIF data for timestamp
    exif = img._getexif() if hasattr(img, '_getexif') else {}
    
    # Try to get date from EXIF, fallback to now
    date_taken = None
    if exif and 36867 in exif:  # DateTimeOriginal
        date_str = exif[36867]
        try:
            date_taken = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
        except:
            pass
    
    if not date_taken:
        date_taken = datetime.now()
    
    # Format date
    if date_format == "dd_slash_mm_yyyy":
        date_text = date_taken.strftime("%d/%m/%Y")
    elif date_format == "mm_slash_dd_yyyy":
        date_text = date_taken.strftime("%m/%d/%Y")
    else:  # yyyy_dash_mm_dd
        date_text = date_taken.strftime("%Y-%m-%d")
    
    # Format time
    if time_format == "24h":
        time_text = date_taken.strftime("%H:%M:%S")
    else:  # 12h
        time_text = date_taken.strftime("%I:%M:%S %p")
    
    full_text = f"{date_text} {time_text}"
    
    # Draw on image
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except:
        font = ImageFont.load_default()
    
    # Position at bottom right with padding
    bbox = draw.textbbox((0, 0), full_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    x = img.width - text_width - 20
    y = img.height - text_height - 20
    
    # Parse color
    rgb_color = tuple(int(color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    
    draw.text((x, y), full_text, fill=rgb_color, font=font)
    
    # Save to bytes
    output = BytesIO()
    img.save(output, format='JPEG', quality=95)
    output.seek(0)
    
    return FileResponse(
        output,
        media_type="image/jpeg",
        headers={"Content-Disposition": "attachment; filename=timestamped.jpg"}
    )

# --- Admin Dashboard ---
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, start: Optional[str] = None, end: Optional[str] = None):
    u = require_admin(request)
    if isinstance(u, (RedirectResponse, HTMLResponse)):
        return u
    
    conn = get_db()
    cur = conn.cursor()
    
    # Get all users
    cur.execute("SELECT * FROM users ORDER BY created_at DESC")
    users = cur.fetchall()
    
    # Build table rows
    rows = []
    for r in users:
        # Safe access to retrofit column
        try:
            retrofit_val = int(r['can_use_retrofit_tool'])
        except (KeyError, TypeError, ValueError):
            retrofit_val = 1
        retrofit_status = "✅ Yes" if retrofit_val == 1 else "❌ No"
        
        # Safe retrofit button
        try:
            retrofit_val = int(r['can_use_retrofit_tool'])
        except (KeyError, TypeError, ValueError):
            retrofit_val = 1
            
        if retrofit_val == 1:
            retrofit_btn = f'<button onclick="toggleRetrofit({r["id"]}, 0)">Block Retrofit</button>'
        else:
            retrofit_btn = f'<button onclick="toggleRetrofit({r["id"]}, 1)">Allow Retrofit</button>'
        
        status = r["subscription_status"]
        if status == "active":
            btn = f'<button onclick="updateStatus({r["id"]}, \'inactive\')">Deactivate</button>'
        else:
            btn = f'<button onclick="updateStatus({r["id"]}, \'active\')">Activate</button>'
        
        rows.append(f"""
            <tr>
                <td>{r["id"]}</td>
                <td>{r["email"]}</td>
                <td>{r["subscription_status"]}</td>
                <td>{r.get("subscription_end_date", "N/A")}</td>
                <td>{retrofit_status}</td>
                <td>{btn}</td>
                <td>{retrofit_btn}</td>
            </tr>
        """)
    
    conn.close()
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Dashboard</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: system-ui, -apple-system, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 2rem;
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                padding: 2rem;
                border-radius: 1rem;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            }}
            h1 {{ color: #667eea; margin-bottom: 2rem; }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 1rem;
            }}
            th, td {{
                padding: 1rem;
                text-align: left;
                border-bottom: 1px solid #e0e0e0;
            }}
            th {{
                background: #f7fafc;
                font-weight: 600;
                color: #2d3748;
            }}
            button {{
                padding: 0.5rem 1rem;
                background: #667eea;
                color: white;
                border: none;
                border-radius: 0.5rem;
                cursor: pointer;
                margin-right: 0.5rem;
            }}
            button:hover {{ opacity: 0.9; }}
            .nav {{ margin-bottom: 2rem; }}
            .nav a {{
                color: #667eea;
                text-decoration: none;
                margin-right: 1rem;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="nav">
                <a href="/tool2">← Back to Tools</a>
            </div>
            <h1>Admin Dashboard</h1>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Email</th>
                        <th>Status</th>
                        <th>End Date</th>
                        <th>Retrofit</th>
                        <th>Actions</th>
                        <th>Retrofit Access</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows)}
                </tbody>
            </table>
        </div>
        <script>
            async function updateStatus(userId, newStatus) {{
                const response = await fetch('/admin/update-status', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ user_id: userId, status: newStatus }})
                }});
                if (response.ok) {{
                    location.reload();
                }}
            }}
            
            async function toggleRetrofit(userId, newValue) {{
                const response = await fetch('/admin/toggle-retrofit', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ user_id: userId, value: newValue }})
                }});
                if (response.ok) {{
                    location.reload();
                }}
            }}
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(html)

@app.post("/admin/update-status")
async def admin_update_status(request: Request):
    u = require_admin(request)
    if isinstance(u, (RedirectResponse, HTMLResponse)):
        return u
    
    data = await request.json()
    user_id = data.get("user_id")
    status = data.get("status")
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET subscription_status=? WHERE id=?", (status, user_id))
    conn.commit()
    conn.close()
    
    return JSONResponse({"success": True})

@app.post("/admin/toggle-retrofit")
async def admin_toggle_retrofit(request: Request):
    u = require_admin(request)
    if isinstance(u, (RedirectResponse, HTMLResponse)):
        return u
    
    data = await request.json()
    user_id = data.get("user_id")
    value = data.get("value")
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET can_use_retrofit_tool=? WHERE id=?", (value, user_id))
    conn.commit()
    conn.close()
    
    return JSONResponse({"success": True})

# --- API Endpoints ---
@app.get("/api/check-retrofit-access")
def api_check_retrofit_access(request: Request):
    """API endpoint to check if user has retrofit tool access"""
    email = get_cookie(request, "user_email")
    if not email:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    row = get_user_row_by_email(email)
    if not row:
        return JSONResponse({"error": "User not found"}, status_code=404)
    
    # Safe access to retrofit column
    try:
        can_use = bool(row['can_use_retrofit_tool'])
    except (KeyError, TypeError):
        can_use = True  # Default to allowing access
    
    return JSONResponse({
        "email": email,
        "can_use_retrofit_tool": can_use
    })

@app.get("/api/ping")
def ping():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.get("/billing", response_class=HTMLResponse)
def billing_page(request: Request):
    row = require_active_user_row(request)
    if isinstance(row, (RedirectResponse, HTMLResponse)):
        return row
    
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Billing - AutoDate</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: system-ui, -apple-system, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 2rem;
            }
            .container {
                background: white;
                padding: 3rem;
                border-radius: 1rem;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                max-width: 600px;
                text-align: center;
            }
            h1 { color: #667eea; margin-bottom: 1rem; }
            p { color: #666; margin-bottom: 2rem; line-height: 1.6; }
            a {
                display: inline-block;
                padding: 1rem 2rem;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                text-decoration: none;
                border-radius: 0.5rem;
                font-weight: 600;
            }
            a:hover { opacity: 0.9; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>💳 Billing Information</h1>
            <p>Your subscription is currently active. For billing inquiries or to manage your subscription, please contact support.</p>
            <a href="/tool2">← Back to Tools</a>
        </div>
    </body>
    </html>
    """)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
