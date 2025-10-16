import os
import io
import csv
import random
import sqlite3
from datetime import datetime, timedelta
from string import Template
from typing import List, Optional

from fastapi import FastAPI, Form, UploadFile, File, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Database Setup ---
def get_db():
    conn = sqlite3.connect("autodate.db")
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
            subscription_status TEXT DEFAULT 'active',
            subscription_end_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- Cookie Helpers ---
def set_cookie(response: Response, key: str, value: str, max_age: int = 86400*30):
    """Set a cookie with 30 day expiry by default"""
    response.set_cookie(
        key=key,
        value=value,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=False  # Set to True in production with HTTPS
    )

def get_cookie(request: Request, key: str) -> Optional[str]:
    return request.cookies.get(key)

def delete_cookie(response: Response, key: str):
    response.delete_cookie(key=key)

# --- User Helpers ---
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

# --- Modern Login/Signup HTML ---
login_html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - AutoDate</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
            max-width: 400px;
            width: 100%;
            animation: slideIn 0.5s ease-out;
        }
        
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(-30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 40px 30px;
            text-align: center;
            color: white;
        }
        
        .header h1 {
            font-size: 32px;
            font-weight: 700;
            margin-bottom: 8px;
        }
        
        .header p {
            font-size: 16px;
            opacity: 0.9;
        }
        
        .form-container {
            padding: 40px 30px;
        }
        
        .form-group {
            margin-bottom: 24px;
        }
        
        label {
            display: block;
            font-size: 14px;
            font-weight: 600;
            color: #333;
            margin-bottom: 8px;
        }
        
        input[type="email"],
        input[type="password"] {
            width: 100%;
            padding: 14px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 16px;
            transition: all 0.3s;
        }
        
        input[type="email"]:focus,
        input[type="password"]:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        
        .btn {
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(102, 126, 234, 0.3);
        }
        
        .btn:active {
            transform: translateY(0);
        }
        
        .divider {
            text-align: center;
            margin: 24px 0;
            position: relative;
        }
        
        .divider::before {
            content: '';
            position: absolute;
            left: 0;
            top: 50%;
            width: 100%;
            height: 1px;
            background: #e0e0e0;
        }
        
        .divider span {
            background: white;
            padding: 0 16px;
            position: relative;
            color: #999;
            font-size: 14px;
        }
        
        .link {
            text-align: center;
            margin-top: 20px;
        }
        
        .link a {
            color: #667eea;
            text-decoration: none;
            font-weight: 600;
            transition: color 0.2s;
        }
        
        .link a:hover {
            color: #764ba2;
        }
        
        .error {
            background: #fee;
            color: #c33;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 14px;
            border-left: 4px solid #c33;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>AutoDate</h1>
            <p>Welcome back! Please login to continue</p>
        </div>
        <div class="form-container">
            $error_msg
            <form method="POST" action="/login">
                <div class="form-group">
                    <label for="email">Email Address</label>
                    <input type="email" id="email" name="email" required placeholder="you@example.com">
                </div>
                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required placeholder="••••••••">
                </div>
                <button type="submit" class="btn">Sign In</button>
            </form>
            <div class="link">
                <p>Don't have an account? <a href="/signup">Sign up</a></p>
            </div>
        </div>
    </div>
</body>
</html>
"""

signup_html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign Up - AutoDate</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
            max-width: 400px;
            width: 100%;
            animation: slideIn 0.5s ease-out;
        }
        
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(-30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 40px 30px;
            text-align: center;
            color: white;
        }
        
        .header h1 {
            font-size: 32px;
            font-weight: 700;
            margin-bottom: 8px;
        }
        
        .header p {
            font-size: 16px;
            opacity: 0.9;
        }
        
        .form-container {
            padding: 40px 30px;
        }
        
        .form-group {
            margin-bottom: 24px;
        }
        
        label {
            display: block;
            font-size: 14px;
            font-weight: 600;
            color: #333;
            margin-bottom: 8px;
        }
        
        input[type="email"],
        input[type="password"] {
            width: 100%;
            padding: 14px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 16px;
            transition: all 0.3s;
        }
        
        input[type="email"]:focus,
        input[type="password"]:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        
        .btn {
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(102, 126, 234, 0.3);
        }
        
        .btn:active {
            transform: translateY(0);
        }
        
        .link {
            text-align: center;
            margin-top: 20px;
        }
        
        .link a {
            color: #667eea;
            text-decoration: none;
            font-weight: 600;
            transition: color 0.2s;
        }
        
        .link a:hover {
            color: #764ba2;
        }
        
        .error {
            background: #fee;
            color: #c33;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 14px;
            border-left: 4px solid #c33;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Create Account</h1>
            <p>Join AutoDate today</p>
        </div>
        <div class="form-container">
            $error_msg
            <form method="POST" action="/signup">
                <div class="form-group">
                    <label for="email">Email Address</label>
                    <input type="email" id="email" name="email" required placeholder="you@example.com">
                </div>
                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required placeholder="••••••••">
                </div>
                <button type="submit" class="btn">Create Account</button>
            </form>
            <div class="link">
                <p>Already have an account? <a href="/login">Sign in</a></p>
            </div>
        </div>
    </div>
</body>
</html>
"""

# --- Routes ---
@app.get("/")
async def root(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    email = user_row["email"]
    return HTMLResponse(f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoDate - Dashboard</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        .header {{
            background: white;
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .header h1 {{
            font-size: 32px;
            color: #333;
        }}
        
        .user-info {{
            text-align: right;
        }}
        
        .user-info p {{
            color: #666;
            margin-bottom: 10px;
        }}
        
        .logout-btn {{
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.2s;
        }}
        
        .logout-btn:hover {{
            background: #764ba2;
            transform: translateY(-2px);
        }}
        
        .tools-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 24px;
        }}
        
        .tool-card {{
            background: white;
            border-radius: 16px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            transition: transform 0.3s, box-shadow 0.3s;
            cursor: pointer;
        }}
        
        .tool-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 15px 40px rgba(0,0,0,0.3);
        }}
        
        .tool-card h2 {{
            font-size: 24px;
            color: #333;
            margin-bottom: 12px;
        }}
        
        .tool-card p {{
            color: #666;
            line-height: 1.6;
            margin-bottom: 20px;
        }}
        
        .tool-btn {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px 24px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            transition: all 0.2s;
        }}
        
        .tool-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>AutoDate Dashboard</h1>
            <div class="user-info">
                <p>Logged in as: <strong>{email}</strong></p>
                <form method="POST" action="/logout" style="display:inline;">
                    <button type="submit" class="logout-btn">Logout</button>
                </form>
            </div>
        </div>
        
        <div class="tools-grid">
            <div class="tool-card">
                <h2>📸 Timestamp Tool</h2>
                <p>Add timestamps to multiple images with custom date ranges and cropping options.</p>
                <a href="/tool/timestamp" class="tool-btn">Open Tool</a>
            </div>
            
            <div class="tool-card">
                <h2>🏠 Retrofit Design Tool</h2>
                <p>Create PAS 2035 compliant retrofit design documents automatically.</p>
                <a href="/tool/retrofit" class="tool-btn">Open Tool</a>
            </div>
            
            <div class="tool-card">
                <h2>⚙️ Admin Panel</h2>
                <p>Manage users and subscriptions.</p>
                <a href="/admin" class="tool-btn">Open Admin</a>
            </div>
        </div>
    </div>
</body>
</html>
    """)

@app.get("/login")
def get_login():
    t = Template(login_html)
    return HTMLResponse(t.substitute(error_msg=""))

@app.post("/login")
def post_login(email: str = Form(...), password: str = Form(...)):
    row = get_user_row_by_email(email)
    
    if not row or row["password"] != password:
        t = Template(login_html)
        return HTMLResponse(t.substitute(error_msg='<div class="error">Invalid email or password</div>'))
    
    response = RedirectResponse("/", status_code=302)
    set_cookie(response, "user_email", email.lower())
    return response

@app.get("/signup")
def get_signup():
    t = Template(signup_html)
    return HTMLResponse(t.substitute(error_msg=""))

@app.post("/signup")
def post_signup(email: str = Form(...), password: str = Form(...)):
    conn = get_db()
    cur = conn.cursor()
    
    try:
        end_date = (datetime.now() + timedelta(days=365)).isoformat()
        cur.execute(
            "INSERT INTO users (email, password, subscription_status, subscription_end_date) VALUES (?, ?, 'active', ?)",
            (email.lower(), password, end_date)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        t = Template(signup_html)
        return HTMLResponse(t.substitute(error_msg='<div class="error">Email already registered</div>'))
    
    conn.close()
    
    response = RedirectResponse("/", status_code=302)
    set_cookie(response, "user_email", email.lower())
    return response

@app.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=302)
    delete_cookie(response, "user_email")
    return response

# --- Timestamp Tool ---
timestamp_tool_html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Timestamp Tool - AutoDate</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }
        
        .container {
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        
        .header {
            text-align: center;
            margin-bottom: 40px;
        }
        
        .header h1 {
            font-size: 36px;
            color: #333;
            margin-bottom: 8px;
        }
        
        .header p {
            color: #666;
            font-size: 16px;
        }
        
        .back-btn {
            display: inline-block;
            color: #667eea;
            text-decoration: none;
            margin-bottom: 20px;
            font-weight: 600;
        }
        
        .back-btn:hover {
            color: #764ba2;
        }
        
        .form-section {
            margin-bottom: 30px;
        }
        
        .form-section h3 {
            color: #333;
            margin-bottom: 16px;
            font-size: 18px;
        }
        
        .drop-zone {
            border: 3px dashed #667eea;
            border-radius: 12px;
            padding: 60px 20px;
            text-align: center;
            background: #f8f9ff;
            cursor: pointer;
            transition: all 0.3s;
            position: relative;
        }
        
        .drop-zone:hover {
            background: #f0f2ff;
            border-color: #764ba2;
        }
        
        .drop-zone.dragover {
            background: #e8ebff;
            border-color: #764ba2;
            transform: scale(1.02);
        }
        
        .drop-zone p {
            color: #667eea;
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 8px;
        }
        
        .drop-zone span {
            color: #999;
            font-size: 14px;
        }
        
        .file-input {
            display: none;
        }
        
        .preview-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            gap: 16px;
            margin-top: 20px;
        }
        
        .preview-item {
            position: relative;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }
        
        .preview-item img {
            width: 100%;
            height: 150px;
            object-fit: cover;
        }
        
        .preview-item .remove {
            position: absolute;
            top: 8px;
            right: 8px;
            background: rgba(255,0,0,0.8);
            color: white;
            border: none;
            border-radius: 50%;
            width: 28px;
            height: 28px;
            cursor: pointer;
            font-size: 16px;
            line-height: 28px;
        }
        
        .preview-item .remove:hover {
            background: red;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            font-weight: 600;
            color: #333;
            margin-bottom: 8px;
        }
        
        .form-group input,
        .form-group select {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
        }
        
        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
        }
        
        .submit-btn {
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .submit-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4);
        }
        
        .submit-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }
        
        .results {
            margin-top: 40px;
            display: none;
        }
        
        .results.show {
            display: block;
        }
        
        .results h3 {
            color: #333;
            margin-bottom: 20px;
        }
        
        .result-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 20px;
        }
        
        .result-item {
            text-align: center;
        }
        
        .result-item img {
            width: 100%;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            margin-bottom: 12px;
        }
        
        .download-btn {
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 8px 16px;
            border-radius: 6px;
            text-decoration: none;
            font-weight: 600;
            transition: all 0.2s;
        }
        
        .download-btn:hover {
            background: #764ba2;
        }
        
        .loading {
            text-align: center;
            padding: 40px;
            display: none;
        }
        
        .loading.show {
            display: block;
        }
        
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="container">
        <a href="/" class="back-btn">← Back to Dashboard</a>
        
        <div class="header">
            <h1>📸 Timestamp Tool</h1>
            <p>Add timestamps to multiple images with time range distribution</p>
        </div>
        
        <form id="timestampForm">
            <div class="form-section">
                <h3>Upload Images</h3>
                <div class="drop-zone" id="dropZone">
                    <p>📁 Drag & Drop Images Here</p>
                    <span>or click to browse (supports multiple images)</span>
                    <input type="file" id="fileInput" class="file-input" accept="image/*" multiple>
                </div>
                <div class="preview-grid" id="previewGrid"></div>
            </div>
            
            <div class="form-section">
                <h3>Timestamp Settings</h3>
                
                <div class="form-group">
                    <label>Date Text</label>
                    <input type="text" id="dateText" value="16/10/2025" required>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label>Start Time</label>
                        <input type="time" id="startTime" value="09:00" required>
                    </div>
                    <div class="form-group">
                        <label>End Time</label>
                        <input type="time" id="endTime" value="17:00" required>
                    </div>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label>Crop from Bottom (pixels)</label>
                        <input type="number" id="cropBottom" value="120" min="0">
                    </div>
                    <div class="form-group">
                        <label>Text Color</label>
                        <select id="textColor">
                            <option value="255,255,255">White</option>
                            <option value="0,0,0">Black</option>
                            <option value="255,0,0">Red</option>
                            <option value="0,255,0">Green</option>
                            <option value="0,0,255">Blue</option>
                        </select>
                    </div>
                </div>
            </div>
            
            <button type="submit" class="submit-btn" id="submitBtn" disabled>Process Images</button>
        </form>
        
        <div class="loading" id="loading">
            <div class="spinner"></div>
            <p>Processing your images...</p>
        </div>
        
        <div class="results" id="results">
            <h3>✅ Processed Images</h3>
            <button onclick="downloadAll()" class="submit-btn" style="margin-bottom: 20px;">📦 Download All Images</button>
            <div class="result-grid" id="resultGrid"></div>
        </div>
    </div>
    
    <script>
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        const previewGrid = document.getElementById('previewGrid');
        const submitBtn = document.getElementById('submitBtn');
        const form = document.getElementById('timestampForm');
        const loading = document.getElementById('loading');
        const results = document.getElementById('results');
        const resultGrid = document.getElementById('resultGrid');
        
        let selectedFiles = [];
        
        // Click to browse
        dropZone.addEventListener('click', () => fileInput.click());
        
        // Drag and drop
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
        
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });
        
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            handleFiles(e.dataTransfer.files);
        });
        
        fileInput.addEventListener('change', (e) => {
            handleFiles(e.target.files);
        });
        
        function handleFiles(files) {
            selectedFiles = Array.from(files);
            displayPreviews();
            submitBtn.disabled = selectedFiles.length === 0;
        }
        
        function displayPreviews() {
            previewGrid.innerHTML = '';
            selectedFiles.forEach((file, index) => {
                const reader = new FileReader();
                reader.onload = (e) => {
                    const div = document.createElement('div');
                    div.className = 'preview-item';
                    div.innerHTML = `
                        <img src="${e.target.result}" alt="Preview">
                        <button class="remove" onclick="removeFile(${index})" type="button">×</button>
                    `;
                    previewGrid.appendChild(div);
                };
                reader.readAsDataURL(file);
            });
        }
        
        window.removeFile = function(index) {
            selectedFiles.splice(index, 1);
            displayPreviews();
            submitBtn.disabled = selectedFiles.length === 0;
        };
        
        let processedImages = [];
        
        window.downloadAll = function() {
            processedImages.forEach((img, index) => {
                const link = document.createElement('a');
                link.href = `data:image/jpeg;base64,${img.data}`;
                link.download = `stamped_${index + 1}.jpg`;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                
                // Small delay between downloads
                if (index < processedImages.length - 1) {
                    setTimeout(() => {}, 100);
                }
            });
        };
        
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            if (selectedFiles.length === 0) return;
            
            const formData = new FormData();
            selectedFiles.forEach(file => formData.append('images', file));
            formData.append('date_text', document.getElementById('dateText').value);
            formData.append('start_time', document.getElementById('startTime').value);
            formData.append('end_time', document.getElementById('endTime').value);
            formData.append('crop_bottom', document.getElementById('cropBottom').value);
            formData.append('text_color', document.getElementById('textColor').value);
            
            submitBtn.disabled = true;
            loading.classList.add('show');
            results.classList.remove('show');
            
            try {
                const response = await fetch('/api/stamp-batch', {
                    method: 'POST',
                    body: formData
                });
                
                const data = await response.json();
                
                loading.classList.remove('show');
                results.classList.add('show');
                
                processedImages = data.images;  // Store for download all
                
                resultGrid.innerHTML = '';
                data.images.forEach((img, index) => {
                    const div = document.createElement('div');
                    div.className = 'result-item';
                    div.innerHTML = `
                        <img src="data:image/jpeg;base64,${img.data}" alt="Result ${index + 1}">
                        <a href="data:image/jpeg;base64,${img.data}" download="stamped_${index + 1}.jpg" class="download-btn">
                            Download
                        </a>
                    `;
                    resultGrid.appendChild(div);
                });
                
                submitBtn.disabled = false;
            } catch (error) {
                alert('Error processing images. Please try again.');
                loading.classList.remove('show');
                submitBtn.disabled = false;
            }
        });
    </script>
</body>
</html>
"""

@app.get("/tool/timestamp")
def get_timestamp_tool(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    return HTMLResponse(timestamp_tool_html)

# Backward compatibility - redirect old URL to new
@app.get("/tool2")
def redirect_tool2(request: Request):
    return RedirectResponse("/tool/timestamp", status_code=301)

# --- Timestamp API with Pillow ---
from PIL import Image, ImageDraw, ImageFont

@app.post("/api/stamp-batch")
async def stamp_batch(
    images: List[UploadFile] = File(...),
    date_text: str = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    crop_bottom: int = Form(120),
    text_color: str = Form("255,255,255")
):
    """Process multiple images with distributed timestamps"""
    
    try:
        # Parse times
        start_h, start_m = map(int, start_time.split(':'))
        end_h, end_m = map(int, end_time.split(':'))
        
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m
        
        num_images = len(images)
        
        # Calculate time interval
        if num_images > 1:
            interval = (end_minutes - start_minutes) / (num_images - 1)
        else:
            interval = 0
        
        # Parse color
        r, g, b = map(int, text_color.split(','))
        
        results = []
        
        for idx, img_file in enumerate(images):
            try:
                # Calculate time for this image
                current_minutes = start_minutes + (interval * idx)
                current_h = int(current_minutes // 60)
                current_m = int(current_minutes % 60)
                time_str = f"{current_h:02d}:{current_m:02d}:{idx*3:02d}"  # Added seconds
                
                # Read image - FIXED: Reset file pointer and validate
                await img_file.seek(0)
                img_bytes = await img_file.read()
                
                if not img_bytes:
                    continue
                
                # Open image with error handling
                img = Image.open(io.BytesIO(img_bytes))
                
                # Convert to RGB if needed
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Crop from bottom if needed
                if crop_bottom > 0:
                    width, height = img.size
                    new_height = max(height - crop_bottom, 100)  # Don't crop too much
                    img = img.crop((0, 0, width, new_height))
                
                # Add timestamp
                draw = ImageDraw.Draw(img)
                
                # Try multiple font paths (different systems have different locations)
                font = None
                font_paths = [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                    "/System/Library/Fonts/Helvetica.ttc",
                    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
                ]
                
                for font_path in font_paths:
                    try:
                        font = ImageFont.truetype(font_path, 38)  # Slightly smaller to match original exactly
                        break
                    except:
                        continue
                
                # Fallback to default if no font found
                if font is None:
                    font = ImageFont.load_default()
                
                # Create timestamp text - format like your example: "03 Apr 2025, 14:34:15"
                timestamp_text = f"{date_text}, {time_str}"
                
                # Get text size
                bbox = draw.textbbox((0, 0), timestamp_text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                
                # Position at BOTTOM RIGHT with padding (like your examples)
                width, height = img.size
                x = width - text_width - 18
                y = height - text_height - 18
                
                # Draw text with black shadow (like your examples)
                shadow_offset = 3
                draw.text((x+shadow_offset, y+shadow_offset), timestamp_text, font=font, fill=(0, 0, 0))
                draw.text((x, y), timestamp_text, font=font, fill=(r, g, b))
                
                # Save to bytes
                output = io.BytesIO()
                img.save(output, format='JPEG', quality=95)
                output.seek(0)
                
                # Base64 encode
                import base64
                img_base64 = base64.b64encode(output.read()).decode()
                
                results.append({
                    "filename": f"stamped_{idx+1}.jpg",
                    "data": img_base64
                })
            
            except Exception as e:
                print(f"Error processing image {idx}: {str(e)}")
                continue
        
        if not results:
            return {"error": "No images could be processed"}, 400
        
        return {"images": results}
    
    except Exception as e:
        print(f"Error in stamp_batch: {str(e)}")
        return {"error": str(e)}, 500

# --- Retrofit Tool (Foundation) ---
retrofit_tool_html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Retrofit Design Tool - AutoDate</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }
        
        .container {
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        
        .header {
            text-align: center;
            margin-bottom: 40px;
        }
        
        .header h1 {
            font-size: 36px;
            color: #333;
            margin-bottom: 8px;
        }
        
        .header p {
            color: #666;
            font-size: 16px;
        }
        
        .back-btn {
            display: inline-block;
            color: #667eea;
            text-decoration: none;
            margin-bottom: 20px;
            font-weight: 600;
        }
        
        .back-btn:hover {
            color: #764ba2;
        }
        
        .progress-bar {
            display: flex;
            justify-content: space-between;
            margin-bottom: 40px;
            position: relative;
        }
        
        .progress-bar::before {
            content: '';
            position: absolute;
            top: 20px;
            left: 0;
            width: 100%;
            height: 3px;
            background: #e0e0e0;
            z-index: 0;
        }
        
        .progress-step {
            text-align: center;
            position: relative;
            z-index: 1;
        }
        
        .progress-step .circle {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            background: #e0e0e0;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 8px;
            font-weight: 600;
            color: #999;
        }
        
        .progress-step.active .circle {
            background: #667eea;
            color: white;
        }
        
        .progress-step .label {
            font-size: 12px;
            color: #999;
        }
        
        .progress-step.active .label {
            color: #667eea;
            font-weight: 600;
        }
        
        .format-tabs {
            display: flex;
            gap: 16px;
            margin-bottom: 30px;
        }
        
        .format-tab {
            flex: 1;
            padding: 20px;
            border: 3px solid #e0e0e0;
            border-radius: 12px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .format-tab:hover {
            border-color: #667eea;
        }
        
        .format-tab.active {
            border-color: #667eea;
            background: #f8f9ff;
        }
        
        .format-tab h3 {
            color: #333;
            margin-bottom: 8px;
        }
        
        .upload-section {
            display: none;
        }
        
        .upload-section.active {
            display: block;
        }
        
        .upload-group {
            margin-bottom: 24px;
        }
        
        .upload-group h4 {
            color: #333;
            margin-bottom: 12px;
        }
        
        .drop-zone {
            border: 3px dashed #667eea;
            border-radius: 12px;
            padding: 40px 20px;
            text-align: center;
            background: #f8f9ff;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .drop-zone:hover {
            background: #f0f2ff;
            border-color: #764ba2;
        }
        
        .drop-zone.dragover {
            background: #e8ebff;
            border-color: #764ba2;
        }
        
        .drop-zone p {
            color: #667eea;
            font-weight: 600;
            margin-bottom: 4px;
        }
        
        .drop-zone span {
            color: #999;
            font-size: 14px;
        }
        
        .file-input {
            display: none;
        }
        
        .file-display {
            margin-top: 12px;
            padding: 12px;
            background: #f0f2ff;
            border-radius: 8px;
            display: none;
        }
        
        .file-display.show {
            display: block;
        }
        
        .file-display p {
            color: #333;
            font-weight: 600;
        }
        
        .file-display span {
            color: #666;
            font-size: 14px;
        }
        
        .submit-btn {
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            margin-top: 30px;
        }
        
        .submit-btn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4);
        }
        
        .submit-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
    </style>
</head>
<body>
    <div class="container">
        <a href="/" class="back-btn">← Back to Dashboard</a>
        
        <div class="header">
            <h1>🏠 Retrofit Design Tool</h1>
            <p>Create PAS 2035 Compliant Retrofit Designs</p>
        </div>
        
        <div class="progress-bar">
            <div class="progress-step active">
                <div class="circle">1</div>
                <div class="label">Upload</div>
            </div>
            <div class="progress-step">
                <div class="circle">2</div>
                <div class="label">Measures</div>
            </div>
            <div class="progress-step">
                <div class="circle">3</div>
                <div class="label">Questions</div>
            </div>
            <div class="progress-step">
                <div class="circle">4</div>
                <div class="label">Calcs</div>
            </div>
            <div class="progress-step">
                <div class="circle">5</div>
                <div class="label">Generate</div>
            </div>
        </div>
        
        <h3 style="margin-bottom: 20px; color: #333;">Step 1: Select Format & Upload Documents</h3>
        
        <div class="format-tabs">
            <div class="format-tab active" onclick="selectFormat('pashub')">
                <h3>PAS Hub</h3>
                <p>Upload PAS Hub site notes + condition report</p>
            </div>
            <div class="format-tab" onclick="selectFormat('elmhurst')">
                <h3>Elmhurst</h3>
                <p>Upload Elmhurst RdSAP + condition report</p>
            </div>
        </div>
        
        <form id="uploadForm">
            <!-- PAS Hub Uploads -->
            <div class="upload-section active" id="pashub-section">
                <div class="upload-group">
                    <h4>📄 PAS Hub Site Notes</h4>
                    <div class="drop-zone" onclick="document.getElementById('pashub-sitenotes').click()">
                        <p>📁 Drop file here or click to browse</p>
                        <span>PDF format</span>
                    </div>
                    <input type="file" id="pashub-sitenotes" class="file-input" accept=".pdf">
                    <div class="file-display" id="pashub-sitenotes-display"></div>
                </div>
                
                <div class="upload-group">
                    <h4>📷 PAS Hub Condition Report</h4>
                    <div class="drop-zone" onclick="document.getElementById('pashub-condition').click()">
                        <p>📁 Drop file here or click to browse</p>
                        <span>PDF format with photos</span>
                    </div>
                    <input type="file" id="pashub-condition" class="file-input" accept=".pdf">
                    <div class="file-display" id="pashub-condition-display"></div>
                </div>
            </div>
            
            <!-- Elmhurst Uploads -->
            <div class="upload-section" id="elmhurst-section">
                <div class="upload-group">
                    <h4>📄 Elmhurst RdSAP Site Notes</h4>
                    <div class="drop-zone" onclick="document.getElementById('elmhurst-sitenotes').click()">
                        <p>📁 Drop file here or click to browse</p>
                        <span>PDF format</span>
                    </div>
                    <input type="file" id="elmhurst-sitenotes" class="file-input" accept=".pdf">
                    <div class="file-display" id="elmhurst-sitenotes-display"></div>
                </div>
                
                <div class="upload-group">
                    <h4>📷 Elmhurst Condition Report</h4>
                    <div class="drop-zone" onclick="document.getElementById('elmhurst-condition').click()">
                        <p>📁 Drop file here or click to browse</p>
                        <span>PDF format with photos</span>
                    </div>
                    <input type="file" id="elmhurst-condition" class="file-input" accept=".pdf">
                    <div class="file-display" id="elmhurst-condition-display"></div>
                </div>
            </div>
            
            <button type="submit" class="submit-btn" id="submitBtn" disabled>
                Continue to Measure Selection →
            </button>
        </form>
    </div>
    
    <script>
        let currentFormat = 'pashub';
        let uploadedFiles = {
            pashub: { sitenotes: null, condition: null },
            elmhurst: { sitenotes: null, condition: null }
        };
        
        function selectFormat(format) {
            currentFormat = format;
            
            // Update tabs
            document.querySelectorAll('.format-tab').forEach(tab => tab.classList.remove('active'));
            event.target.closest('.format-tab').classList.add('active');
            
            // Update sections
            document.querySelectorAll('.upload-section').forEach(section => section.classList.remove('active'));
            document.getElementById(format + '-section').classList.add('active');
            
            updateSubmitButton();
        }
        
        // File input handlers
        ['pashub-sitenotes', 'pashub-condition', 'elmhurst-sitenotes', 'elmhurst-condition'].forEach(id => {
            const input = document.getElementById(id);
            input.addEventListener('change', (e) => handleFileSelect(e, id));
        });
        
        function handleFileSelect(e, inputId) {
            const file = e.target.files[0];
            if (!file) return;
            
            const [format, type] = inputId.split('-');
            uploadedFiles[format][type] = file;
            
            // Display file info
            const display = document.getElementById(inputId + '-display');
            display.classList.add('show');
            display.innerHTML = `
                <p>✅ ${file.name}</p>
                <span>${(file.size / 1024 / 1024).toFixed(2)} MB</span>
            `;
            
            updateSubmitButton();
        }
        
        function updateSubmitButton() {
            const btn = document.getElementById('submitBtn');
            const files = uploadedFiles[currentFormat];
            btn.disabled = !files.sitenotes || !files.condition;
        }
        
        document.getElementById('uploadForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            alert('Upload successful! Moving to Step 2 (Coming next!)');
        });
    </script>
</body>
</html>
"""

@app.get("/tool/retrofit")
def get_retrofit_tool(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    return HTMLResponse(retrofit_tool_html)

# --- Admin Panel ---
@app.get("/admin")
def admin_panel(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    
    table_rows = ""
    for r in rows:
        end_date = r["subscription_end_date"] if r["subscription_end_date"] else "N/A"
        status_color = "#4caf50" if r["subscription_status"] == "active" else "#f44336"
        action_btn = f'''
            <form method="POST" action="/admin/toggle-status" style="display:inline;">
                <input type="hidden" name="user_id" value="{r['id']}">
                <input type="hidden" name="current_status" value="{r['subscription_status']}">
                <button type="submit" style="background: {status_color}; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-weight: 600;">
                    {'Suspend' if r['subscription_status'] == 'active' else 'Activate'}
                </button>
            </form>
        '''
        table_rows += f"""
            <tr>
                <td>{r["id"]}</td>
                <td>{r["email"]}</td>
                <td><span style="color: {status_color}; font-weight: 600;">{r["subscription_status"]}</span></td>
                <td>{end_date}</td>
                <td>{r["created_at"]}</td>
                <td>{action_btn}</td>
            </tr>
        """
    
    return HTMLResponse(f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Panel - AutoDate</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }}
        
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 40px;
        }}
        
        .header h1 {{
            font-size: 32px;
            color: #333;
        }}
        
        .back-btn {{
            background: #667eea;
            color: white;
            padding: 10px 20px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
        }}
        
        .back-btn:hover {{
            background: #764ba2;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        th {{
            background: #f5f5f5;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            color: #333;
            border-bottom: 2px solid #e0e0e0;
        }}
        
        td {{
            padding: 12px;
            border-bottom: 1px solid #e0e0e0;
            color: #666;
        }}
        
        tr:hover {{
            background: #f9f9f9;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚙️ Admin Panel</h1>
            <a href="/" class="back-btn">← Back to Dashboard</a>
        </div>
        
        <h2 style="margin-bottom: 20px; color: #333;">Users</h2>
        
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Email</th>
                    <th>Status</th>
                    <th>Subscription End</th>
                    <th>Created</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
    </div>
</body>
</html>
    """)

@app.post("/admin/toggle-status")
def toggle_user_status(request: Request, user_id: int = Form(...), current_status: str = Form(...)):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    # Toggle status
    new_status = "suspended" if current_status == "active" else "active"
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET subscription_status=? WHERE id=?", (new_status, user_id))
    conn.commit()
    conn.close()
    
    return RedirectResponse("/admin", status_code=302)

# --- Ping endpoint ---
@app.get("/api/ping")
def ping():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
