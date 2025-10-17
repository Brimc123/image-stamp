import os
import io
import csv
import random
import sqlite3
from datetime import datetime, timedelta
from string import Template
from typing import List, Optional

from fastapi import FastAPI, Form, UploadFile, File, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageDraw, ImageFont
import zipfile

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Admin Configuration ---
ADMIN_EMAIL = "brimc123@hotmail.com"
ADMIN_PASSWORD = "Dylan1981!!"

# --- Database ---
DB_PATH = "users.db"

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
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            credits REAL DEFAULT 0.0,
            is_active INTEGER DEFAULT 1,
            timestamp_tool_access INTEGER DEFAULT 1,
            retrofit_tool_access INTEGER DEFAULT 1
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            type TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- Helper Functions ---
def is_admin(request: Request) -> bool:
    email = request.cookies.get("user_email")
    return email == ADMIN_EMAIL

def set_cookie(response: Response, key: str, value: str):
    response.set_cookie(key=key, value=value, httponly=True, samesite="lax")

def delete_cookie(response: Response, key: str):
    response.delete_cookie(key=key)

def get_user_row_by_email(email: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cur.fetchone()
    conn.close()
    return row

def require_active_user_row(request: Request):
    email = request.cookies.get("user_email")
    if not email:
        return RedirectResponse(url="/login", status_code=302)
    user_row = get_user_row_by_email(email)
    if not user_row:
        return RedirectResponse(url="/login", status_code=302)
    if user_row["is_active"] == 0 and email != ADMIN_EMAIL:
        return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Account Suspended</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .container {
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 10px 25px rgba(0,0,0,0.2);
                        text-align: center;
                        max-width: 400px;
                    }
                    h1 { color: #e74c3c; margin-bottom: 20px; }
                    p { color: #555; margin-bottom: 30px; }
                    a {
                        display: inline-block;
                        padding: 12px 30px;
                        background: #667eea;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        transition: background 0.3s;
                    }
                    a:hover { background: #764ba2; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>⚠️ Account Suspended</h1>
                    <p>Your account has been suspended. Please contact the administrator for assistance.</p>
                    <a href="/logout">Logout</a>
                </div>
            </body>
            </html>
        """)
    return user_row

# --- Login Page ---
@app.get("/login")
def get_login():
    html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>Login - AutoDate</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }
        .login-container {
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.2);
            width: 100%;
            max-width: 400px;
        }
        h1 {
            text-align: center;
            color: #333;
            margin-bottom: 30px;
            font-size: 28px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #555;
            font-weight: 500;
        }
        input {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        input:focus {
            outline: none;
            border-color: #667eea;
        }
        button {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        .signup-link {
            text-align: center;
            margin-top: 20px;
            color: #666;
        }
        .signup-link a {
            color: #667eea;
            text-decoration: none;
            font-weight: 600;
        }
        .signup-link a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <h1>🔐 Login to AutoDate</h1>
        <form method="POST" action="/login">
            <div class="form-group">
                <label>Email</label>
                <input type="email" name="email" required placeholder="your@email.com">
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" required placeholder="••••••••">
            </div>
            <button type="submit">Login</button>
        </form>
        <div class="signup-link">
            Don't have an account? <a href="/signup">Sign up</a>
        </div>
    </div>
</body>
</html>
    """
    return HTMLResponse(html_content)

@app.post("/login")
def post_login(email: str = Form(...), password: str = Form(...)):
    user_row = get_user_row_by_email(email)
    if not user_row or user_row["password"] != password:
        return HTMLResponse("""
            <script>
                alert("Invalid credentials!");
                window.location.href = "/login";
            </script>
        """)
    resp = RedirectResponse(url="/", status_code=302)
    set_cookie(resp, "user_email", email)
    return resp

# --- Signup Page ---
@app.get("/signup")
def get_signup():
    html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>Sign Up - AutoDate</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }
        .signup-container {
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.2);
            width: 100%;
            max-width: 400px;
        }
        h1 {
            text-align: center;
            color: #333;
            margin-bottom: 30px;
            font-size: 28px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #555;
            font-weight: 500;
        }
        input {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        input:focus {
            outline: none;
            border-color: #667eea;
        }
        button {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        .login-link {
            text-align: center;
            margin-top: 20px;
            color: #666;
        }
        .login-link a {
            color: #667eea;
            text-decoration: none;
            font-weight: 600;
        }
        .login-link a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="signup-container">
        <h1>📝 Create Account</h1>
        <form method="POST" action="/signup">
            <div class="form-group">
                <label>Email</label>
                <input type="email" name="email" required placeholder="your@email.com">
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" required placeholder="••••••••">
            </div>
            <button type="submit">Sign Up</button>
        </form>
        <div class="login-link">
            Already have an account? <a href="/login">Login</a>
        </div>
    </div>
</body>
</html>
    """
    return HTMLResponse(html_content)

@app.post("/signup")
def post_signup(email: str = Form(...), password: str = Form(...)):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (email, password, credits) VALUES (?, ?, ?)", (email, password, 0.0))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return HTMLResponse("""
            <script>
                alert("Email already exists!");
                window.location.href = "/signup";
            </script>
        """)
    conn.close()
    resp = RedirectResponse(url="/", status_code=302)
    set_cookie(resp, "user_email", email)
    return resp

# --- Logout ---
@app.get("/logout")
def logout():
    resp = RedirectResponse(url="/login", status_code=302)
    delete_cookie(resp, "user_email")
    return resp

# --- Dashboard ---
@app.get("/")
async def root(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    email = user_row["email"]
    user_is_admin = is_admin(request)
    credits = user_row["credits"] if "credits" in user_row.keys() else 0.0
    
    has_timestamp_access = user_row["timestamp_tool_access"] == 1
    has_retrofit_access = user_row["retrofit_tool_access"] == 1
    
    billing_card_html = """
        <div class="tool-card">
            <h2>💳 Billing & Credits</h2>
            <p>Manage your account credits and view transaction history.</p>
            <a href="/billing" class="tool-button">View Billing</a>
        </div>
    """
    
    admin_card_html = ""
    if user_is_admin:
        admin_card_html = """
            <div class="tool-card admin-card">
                <h2>⚙️ Admin Panel</h2>
                <p>Manage users, suspensions, and view all billing.</p>
                <a href="/admin" class="tool-button">Open Admin</a>
            </div>
        """
    
    timestamp_card = f"""
        <div class="tool-card {'disabled-card' if not has_timestamp_access else ''}">
            <h2>📸 Timestamp Tool</h2>
            <p>Add timestamps to multiple images with custom date ranges and cropping options.</p>
            {'<a href="/tool/timestamp" class="tool-button">Open Tool</a>' if has_timestamp_access else '<span class="disabled-text">❌ Access Suspended</span>'}
        </div>
    """
    
    retrofit_card = f"""
        <div class="tool-card {'disabled-card' if not has_retrofit_access else ''}">
            <h2>🏠 Retrofit Design Tool</h2>
            <p>Generate PAS 2035 compliant retrofit designs with automated questioning.</p>
            {'<a href="/tool/retrofit" class="tool-button">Open Tool</a>' if has_retrofit_access else '<span class="disabled-text">❌ Access Suspended</span>'}
        </div>
    """
    
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Dashboard - AutoDate</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .header {{
            background: white;
            padding: 20px 40px;
            border-radius: 15px;
            margin-bottom: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }}
        .header h1 {{
            color: #333;
            font-size: 32px;
        }}
        .user-info {{
            display: flex;
            align-items: center;
            gap: 20px;
        }}
        .credits {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 10px 20px;
            border-radius: 25px;
            font-weight: 600;
            font-size: 36pt;
        }}
        .logout-btn {{
            padding: 10px 25px;
            background: #e74c3c;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            transition: background 0.3s;
        }}
        .logout-btn:hover {{
            background: #c0392b;
        }}
        .tools-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            max-width: 1200px;
            margin: 0 auto;
        }}
        .tool-card {{
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s, box-shadow 0.3s;
        }}
        .tool-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 25px rgba(0,0,0,0.15);
        }}
        .tool-card h2 {{
            color: #333;
            margin-bottom: 15px;
            font-size: 24px;
        }}
        .tool-card p {{
            color: #666;
            margin-bottom: 20px;
            line-height: 1.6;
        }}
        .tool-button {{
            display: inline-block;
            padding: 12px 30px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            transition: transform 0.2s;
        }}
        .tool-button:hover {{
            transform: scale(1.05);
        }}
        .admin-card {{
            border: 3px solid #f39c12;
            background: linear-gradient(135deg, #fff9e6 0%, #ffe6cc 100%);
        }}
        .disabled-card {{
            opacity: 0.5;
            background: #f5f5f5;
        }}
        .disabled-text {{
            color: #e74c3c;
            font-weight: 600;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 AutoDate Dashboard</h1>
        <div class="user-info">
            <div class="credits">£{credits:.2f}</div>
            <a href="/logout" class="logout-btn">Logout</a>
        </div>
    </div>
    
    <div class="tools-grid">
        {timestamp_card}
        {retrofit_card}
        {billing_card_html}
        {admin_card_html}
    </div>
</body>
</html>
    """
    return HTMLResponse(html_content)

# --- Billing & Credits ---
@app.get("/billing")
def get_billing(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    email = user_row["email"]
    user_id = user_row["id"]
    credits = user_row["credits"] if "credits" in user_row.keys() else 0.0
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    transactions = cur.fetchall()
    conn.close()
    
    transaction_rows = ""
    for t in transactions:
        color = "#4caf50" if t["amount"] > 0 else "#f44336"
        transaction_rows += f"""
            <tr>
                <td>{t["created_at"]}</td>
                <td>{t["type"].upper()}</td>
                <td style="color: {color}; font-weight: 600;">£{t["amount"]:.2f}</td>
            </tr>
        """
    
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Billing - AutoDate</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
        }}
        h1 {{
            color: #333;
            margin-bottom: 30px;
            font-size: 32px;
        }}
        .credits-display {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            text-align: center;
            margin-bottom: 30px;
        }}
        .credits-display h2 {{
            font-size: 48px;
            margin-bottom: 10px;
        }}
        .topup-btn {{
            display: inline-block;
            padding: 15px 40px;
            background: #4caf50;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 18px;
            transition: background 0.3s;
            margin-bottom: 30px;
        }}
        .topup-btn:hover {{
            background: #45a049;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        th, td {{
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid #e0e0e0;
        }}
        th {{
            background: #f5f5f5;
            font-weight: 600;
            color: #555;
        }}
        .back-btn {{
            display: inline-block;
            padding: 12px 30px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            margin-top: 20px;
        }}
        .back-btn:hover {{
            background: #764ba2;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>💳 Billing & Credits</h1>
        
        <div class="credits-display">
            <h2>£{credits:.2f}</h2>
            <p>Available Credits</p>
        </div>
        
        <a href="/topup" class="topup-btn">💰 Top Up Credits</a>
        
        <h2>Transaction History</h2>
        <table>
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Type</th>
                    <th>Amount</th>
                </tr>
            </thead>
            <tbody>
                {transaction_rows if transaction_rows else '<tr><td colspan="3" style="text-align: center; color: #999;">No transactions yet</td></tr>'}
            </tbody>
        </table>
        
        <a href="/" class="back-btn">← Back to Dashboard</a>
    </div>
</body>
</html>
    """
    return HTMLResponse(html_content)

@app.get("/topup")
def get_topup(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>Top Up - AutoDate</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
            max-width: 500px;
            width: 100%;
        }
        h1 {
            color: #333;
            margin-bottom: 20px;
            font-size: 32px;
            text-align: center;
        }
        .info-box {
            background: #e8f4f8;
            border-left: 4px solid #2196F3;
            padding: 15px;
            margin-bottom: 30px;
            border-radius: 5px;
        }
        .info-box p {
            color: #555;
            line-height: 1.6;
        }
        .form-group {
            margin-bottom: 25px;
        }
        label {
            display: block;
            margin-bottom: 10px;
            color: #555;
            font-weight: 600;
        }
        input {
            width: 100%;
            padding: 15px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
        }
        input:focus {
            outline: none;
            border-color: #667eea;
        }
        button {
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #4caf50 0%, #45a049 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }
        button:hover {
            transform: translateY(-2px);
        }
        .back-link {
            display: block;
            text-align: center;
            margin-top: 20px;
            color: #667eea;
            text-decoration: none;
            font-weight: 600;
        }
        .back-link:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>💰 Top Up Credits</h1>
        
        <div class="info-box">
            <p><strong>Pricing:</strong> £5 per image processing</p>
            <p><strong>Minimum top-up:</strong> £50</p>
            <p>Credits are deducted automatically when processing images.</p>
        </div>
        
        <form method="POST" action="/topup">
            <div class="form-group">
                <label>Top-up Amount (£)</label>
                <input type="number" name="amount" min="50" step="0.01" value="50" required>
            </div>
            <button type="submit">Add Credits</button>
        </form>
        
        <a href="/billing" class="back-link">← Back to Billing</a>
    </div>
</body>
</html>
    """
    return HTMLResponse(html_content)

@app.post("/topup")
def post_topup(request: Request, amount: float = Form(...)):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    if amount < 50:
        return HTMLResponse("""
            <script>
                alert("Minimum top-up is £50");
                window.location.href = "/topup";
            </script>
        """)
    
    user_id = user_row["id"]
    current_credits = user_row["credits"] if "credits" in user_row.keys() else 0.0
    new_credits = current_credits + amount
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET credits = ? WHERE id = ?", (new_credits, user_id))
    cur.execute("INSERT INTO transactions (user_id, amount, type) VALUES (?, ?, ?)", 
                (user_id, amount, "topup"))
    conn.commit()
    conn.close()
    
    return HTMLResponse("""
        <script>
            alert("Credits added successfully!");
            window.location.href = "/billing";
        </script>
    """)

# --- Admin Panel ---
@app.get("/admin")
def admin_panel(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    admin_check = is_admin(request)
    if not admin_check:
        return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Access Denied</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .container {
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 10px 25px rgba(0,0,0,0.2);
                        text-align: center;
                        max-width: 400px;
                    }
                    h1 { color: #e74c3c; margin-bottom: 20px; }
                    p { color: #555; margin-bottom: 30px; }
                    a {
                        display: inline-block;
                        padding: 12px 30px;
                        background: #667eea;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        transition: background 0.3s;
                    }
                    a:hover { background: #764ba2; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🚫 Access Denied</h1>
                    <p>You do not have permission to access the admin panel.</p>
                    <a href="/">Back to Dashboard</a>
                </div>
            </body>
            </html>
        """)
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users ORDER BY created_at DESC")
    users = cur.fetchall()
    conn.close()
    
    user_rows_html = ""
    for u in users:
        status_color = "#4caf50" if u["is_active"] == 1 else "#f44336"
        status_text = "Active" if u["is_active"] == 1 else "Suspended"
        toggle_text = "Suspend" if u["is_active"] == 1 else "Activate"
        
        timestamp_badge = "✓ Timestamp" if u["timestamp_tool_access"] == 1 else "✗ Timestamp"
        timestamp_color = "#4caf50" if u["timestamp_tool_access"] == 1 else "#f44336"
        
        retrofit_badge = "✓ Retrofit" if u["retrofit_tool_access"] == 1 else "✗ Retrofit"
        retrofit_color = "#4caf50" if u["retrofit_tool_access"] == 1 else "#f44336"
        
        user_rows_html += f"""
            <tr>
                <td>{u["email"]}</td>
                <td>£{u["credits"]:.2f}</td>
                <td><span style="color: {status_color}; font-weight: 600;">{status_text}</span></td>
                <td>
                    <span style="background: {timestamp_color}; color: white; padding: 5px 10px; border-radius: 5px; font-size: 12px; margin-right: 5px;">{timestamp_badge}</span>
                    <span style="background: {retrofit_color}; color: white; padding: 5px 10px; border-radius: 5px; font-size: 12px;">{retrofit_badge}</span>
                </td>
                <td>
                    <form method="POST" action="/admin/toggle-status" style="display: inline;">
                        <input type="hidden" name="user_id" value="{u["id"]}">
                        <input type="hidden" name="current_status" value="{u["is_active"]}">
                        <button type="submit" style="padding: 8px 15px; background: #ff9800; color: white; border: none; border-radius: 5px; cursor: pointer; margin-right: 5px;">{toggle_text}</button>
                    </form>
                    <form method="POST" action="/admin/toggle-timestamp" style="display: inline;">
                        <input type="hidden" name="user_id" value="{u["id"]}">
                        <input type="hidden" name="current_access" value="{u["timestamp_tool_access"]}">
                        <button type="submit" style="padding: 8px 15px; background: #2196F3; color: white; border: none; border-radius: 5px; cursor: pointer; margin-right: 5px;">Toggle TS</button>
                    </form>
                    <form method="POST" action="/admin/toggle-retrofit" style="display: inline;">
                        <input type="hidden" name="user_id" value="{u["id"]}">
                        <input type="hidden" name="current_access" value="{u["retrofit_tool_access"]}">
                        <button type="submit" style="padding: 8px 15px; background: #9C27B0; color: white; border: none; border-radius: 5px; cursor: pointer;">Toggle RF</button>
                    </form>
                </td>
            </tr>
        """
    
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Admin Panel - AutoDate</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
        }}
        h1 {{
            color: #333;
            margin-bottom: 30px;
            font-size: 32px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        th, td {{
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid #e0e0e0;
        }}
        th {{
            background: #f5f5f5;
            font-weight: 600;
            color: #555;
        }}
        .actions {{
            display: flex;
            gap: 10px;
            margin-bottom: 30px;
        }}
        .actions a {{
            padding: 12px 25px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
        }}
        .actions a:hover {{
            background: #764ba2;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>⚙️ Admin Panel</h1>
        
        <div class="actions">
            <a href="/">← Back to Dashboard</a>
            <a href="/admin/billing">💳 View All Billing</a>
        </div>
        
        <h2>User Management</h2>
        <table>
            <thead>
                <tr>
                    <th>Email</th>
                    <th>Credits</th>
                    <th>Status</th>
                    <th>Tool Access</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {user_rows_html}
            </tbody>
        </table>
    </div>
</body>
</html>
    """
    return HTMLResponse(html_content)

@app.post("/admin/toggle-status")
def toggle_user_status(request: Request, user_id: int = Form(...), current_status: str = Form(...)):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    if not is_admin(request):
        return HTMLResponse("<script>alert('Access denied!'); window.location.href='/';</script>")
    
    new_status = 0 if int(current_status) == 1 else 1
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_status, user_id))
    conn.commit()
    conn.close()
    
    return RedirectResponse(url="/admin", status_code=302)

@app.post("/admin/toggle-timestamp")
def toggle_timestamp_access(request: Request, user_id: int = Form(...), current_access: str = Form(...)):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    if not is_admin(request):
        return HTMLResponse("<script>alert('Access denied!'); window.location.href='/';</script>")
    
    new_access = 0 if int(current_access) == 1 else 1
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET timestamp_tool_access = ? WHERE id = ?", (new_access, user_id))
    conn.commit()
    conn.close()
    
    return RedirectResponse(url="/admin", status_code=302)

@app.post("/admin/toggle-retrofit")
def toggle_retrofit_access(request: Request, user_id: int = Form(...), current_access: str = Form(...)):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    if not is_admin(request):
        return HTMLResponse("<script>alert('Access denied!'); window.location.href='/';</script>")
    
    new_access = 0 if int(current_access) == 1 else 1
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET retrofit_tool_access = ? WHERE id = ?", (new_access, user_id))
    conn.commit()
    conn.close()
    
    return RedirectResponse(url="/admin", status_code=302)

@app.get("/admin/billing")
def admin_billing(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    admin_check = is_admin(request)
    if not admin_check:
        return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Access Denied</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .container {
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 10px 25px rgba(0,0,0,0.2);
                        text-align: center;
                        max-width: 400px;
                    }
                    h1 { color: #e74c3c; margin-bottom: 20px; }
                    p { color: #555; margin-bottom: 30px; }
                    a {
                        display: inline-block;
                        padding: 12px 30px;
                        background: #667eea;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        transition: background 0.3s;
                    }
                    a:hover { background: #764ba2; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🚫 Access Denied</h1>
                    <p>You do not have permission to access admin billing.</p>
                    <a href="/">Back to Dashboard</a>
                </div>
            </body>
            </html>
        """)
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT t.*, u.email 
        FROM transactions t 
        JOIN users u ON t.user_id = u.id 
        ORDER BY t.created_at DESC
    """)
    transactions = cur.fetchall()
    conn.close()
    
    transaction_rows = ""
    for t in transactions:
        color = "#4caf50" if t["amount"] > 0 else "#f44336"
        transaction_rows += f"""
            <tr>
                <td>{t["created_at"]}</td>
                <td>{t["email"]}</td>
                <td>{t["type"].upper()}</td>
                <td style="color: {color}; font-weight: 600;">£{t["amount"]:.2f}</td>
            </tr>
        """
    
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Admin Billing - AutoDate</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
        }}
        h1 {{
            color: #333;
            margin-bottom: 30px;
            font-size: 32px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        th, td {{
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid #e0e0e0;
        }}
        th {{
            background: #f5f5f5;
            font-weight: 600;
            color: #555;
        }}
        .back-btn {{
            display: inline-block;
            padding: 12px 30px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            margin-bottom: 20px;
        }}
        .back-btn:hover {{
            background: #764ba2;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>💳 All Billing Transactions</h1>
        <a href="/admin" class="back-btn">← Back to Admin</a>
        
        <table>
            <thead>
                <tr>
                    <th>Date</th>
                    <th>User</th>
                    <th>Type</th>
                    <th>Amount</th>
                </tr>
            </thead>
            <tbody>
                {transaction_rows if transaction_rows else '<tr><td colspan="4" style="text-align: center; color: #999;">No transactions yet</td></tr>'}
            </tbody>
        </table>
    </div>
</body>
</html>
    """
    return HTMLResponse(html_content)

# --- Timestamp Tool ---
@app.get("/tool/timestamp")
def get_timestamp_tool(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    if user_row["timestamp_tool_access"] == 0:
        return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Access Denied</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .container {
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 10px 25px rgba(0,0,0,0.2);
                        text-align: center;
                        max-width: 400px;
                    }
                    h1 { color: #e74c3c; margin-bottom: 20px; }
                    p { color: #555; margin-bottom: 30px; }
                    a {
                        display: inline-block;
                        padding: 12px 30px;
                        background: #667eea;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        transition: background 0.3s;
                    }
                    a:hover { background: #764ba2; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🚫 Access Denied</h1>
                    <p>Your access to the Timestamp Tool has been suspended. Please contact the administrator.</p>
                    <a href="/">Back to Dashboard</a>
                </div>
            </body>
            </html>
        """)
    
    credits = user_row["credits"] if "credits" in user_row.keys() else 0.0
    
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Timestamp Tool - AutoDate</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .header {{
            background: white;
            padding: 20px 40px;
            border-radius: 15px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }}
        .header h1 {{
            color: #333;
            font-size: 28px;
        }}
        .credits {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 10px 20px;
            border-radius: 25px;
            font-weight: 600;
            font-size: 36pt;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
            max-width: 800px;
            margin: 0 auto;
        }}
        h2 {{
            color: #333;
            margin-bottom: 20px;
        }}
        .form-group {{
            margin-bottom: 25px;
        }}
        label {{
            display: block;
            margin-bottom: 10px;
            color: #555;
            font-weight: 600;
        }}
        input[type="file"],
        input[type="date"],
        input[type="number"],
        input[type="text"],
        select {{
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
        }}
        input:focus, select:focus {{
            outline: none;
            border-color: #667eea;
        }}
        button {{
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }}
        button:hover {{
            transform: translateY(-2px);
        }}
        .back-btn {{
            display: inline-block;
            padding: 12px 30px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            margin-top: 20px;
        }}
        .back-btn:hover {{
            background: #764ba2;
        }}
        .info-box {{
            background: #e8f4f8;
            border-left: 4px solid #2196F3;
            padding: 15px;
            margin-bottom: 25px;
            border-radius: 5px;
        }}
        .info-box p {{
            color: #555;
            margin: 5px 0;
        }}
        #status {{
            margin-top: 20px;
            padding: 15px;
            border-radius: 8px;
            display: none;
        }}
        .success {{
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }}
        .error {{
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📸 Timestamp Tool</h1>
        <div class="credits">£{credits:.2f}</div>
    </div>

    <div class="container">
        <div class="info-box">
            <p><strong>Cost:</strong> £5 per batch</p>
            <p><strong>Your Credits:</strong> £{credits:.2f}</p>
        </div>

        <form id="stampForm" enctype="multipart/form-data">
            <div class="form-group">
                <label>Upload Images (multiple)</label>
                <input type="file" name="files" id="files" multiple accept="image/*" required>
            </div>

            <div class="form-group">
                <label>Start Date</label>
                <input type="date" name="start_date" id="start_date" required>
            </div>

            <div class="form-group">
                <label>End Date</label>
                <input type="date" name="end_date" id="end_date" required>
            </div>

            <div class="form-group">
                <label>Font Size</label>
                <input type="number" name="font_size" id="font_size" value="36" min="10" max="200" required>
            </div>

            <div class="form-group">
                <label>Font Color</label>
                <select name="font_color" id="font_color">
                    <option value="red">Red</option>
                    <option value="white">White</option>
                    <option value="black">Black</option>
                    <option value="yellow">Yellow</option>
                    <option value="blue">Blue</option>
                </select>
            </div>

            <div class="form-group">
                <label>Crop Height from Bottom (pixels)</label>
                <input type="number" name="crop_height" id="crop_height" value="0" min="0" required>
            </div>

            <button type="submit">🚀 Process Images</button>
        </form>

        <div id="status"></div>

        <a href="/" class="back-btn">← Back to Dashboard</a>
    </div>

    <script>
        document.getElementById('stampForm').addEventListener('submit', async (e) => {{
            e.preventDefault();
            
            const statusDiv = document.getElementById('status');
            statusDiv.style.display = 'block';
            statusDiv.className = '';
            statusDiv.textContent = 'Processing...';
            
            const formData = new FormData();
            const files = document.getElementById('files').files;
            
            for (let i = 0; i < files.length; i++) {{
                formData.append('files', files[i]);
            }}
            
            formData.append('start_date', document.getElementById('start_date').value);
            formData.append('end_date', document.getElementById('end_date').value);
            formData.append('font_size', document.getElementById('font_size').value);
            formData.append('font_color', document.getElementById('font_color').value);
            formData.append('crop_height', document.getElementById('crop_height').value);
            
            try {{
                const response = await fetch('/api/stamp-batch', {{
                    method: 'POST',
                    body: formData
                }});
                
                if (response.ok) {{
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'timestamped_images.zip';
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    
                    statusDiv.className = 'success';
                    statusDiv.textContent = '✓ Success! Your images have been downloaded.';
                }} else {{
                    const error = await response.text();
                    statusDiv.className = 'error';
                    statusDiv.textContent = error || 'Error processing images';
                }}
            }} catch (error) {{
                statusDiv.className = 'error';
                statusDiv.textContent = 'Network error: ' + error.message;
            }}
        }});
    </script>
</body>
</html>
    """
    return HTMLResponse(html_content)

# --- Retrofit Tool ---
@app.get("/tool/retrofit")
def get_retrofit_tool(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    if user_row["retrofit_tool_access"] == 0:
        return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Access Denied</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .container {
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 10px 25px rgba(0,0,0,0.2);
                        text-align: center;
                        max-width: 400px;
                    }
                    h1 { color: #e74c3c; margin-bottom: 20px; }
                    p { color: #555; margin-bottom: 30px; }
                    a {
                        display: inline-block;
                        padding: 12px 30px;
                        background: #667eea;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        transition: background 0.3s;
                    }
                    a:hover { background: #764ba2; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🚫 Access Denied</h1>
                    <p>Your access to the Retrofit Design Tool has been suspended. Please contact the administrator.</p>
                    <a href="/">Back to Dashboard</a>
                </div>
            </body>
            </html>
        """)
    
    html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>Retrofit Design Tool - AutoDate</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
            max-width: 800px;
            margin: 0 auto;
        }
        h1 {
            color: #333;
            margin-bottom: 30px;
            font-size: 32px;
        }
        .info-box {
            background: #e8f4f8;
            border-left: 4px solid #2196F3;
            padding: 20px;
            margin-bottom: 30px;
            border-radius: 5px;
        }
        .info-box h2 {
            color: #2196F3;
            margin-bottom: 15px;
        }
        .info-box p {
            color: #555;
            line-height: 1.6;
            margin-bottom: 10px;
        }
        .back-btn {
            display: inline-block;
            padding: 12px 30px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
        }
        .back-btn:hover {
            background: #764ba2;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🏠 Retrofit Design Tool</h1>
        
        <div class="info-box">
            <h2>Coming Soon!</h2>
            <p>The Retrofit Design Tool is currently under development.</p>
            <p>This tool will help you generate PAS 2035 compliant retrofit designs with:</p>
            <ul style="margin-left: 20px; color: #555;">
                <li>Automated data extraction from site notes</li>
                <li>Measure-specific questioning system</li>
                <li>Integration with solar and heat pump calculations</li>
                <li>Audit-proof document generation</li>
            </ul>
        </div>
        
        <a href="/" class="back-btn">← Back to Dashboard</a>
    </div>
</body>
</html>
    """
    return HTMLResponse(html_content)

# --- API Endpoints ---
@app.post("/api/stamp-batch")
async def stamp_batch(
    request: Request,
    files: List[UploadFile] = File(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    font_size:
