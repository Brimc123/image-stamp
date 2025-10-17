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

# --- Admin Configuration ---
ADMIN_EMAIL = "brimc123@hotmail.com"  # Main admin user
ADMIN_PASSWORD = "Dylan1981!!"  # Admin password

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
            credits REAL DEFAULT 0.0,
            timestamp_tool_access INTEGER DEFAULT 1,
            retrofit_tool_access INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
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

def is_admin(request: Request) -> bool:
    """Check if current user is admin"""
    email = get_cookie(request, "user_email")
    return email and email.lower() == ADMIN_EMAIL.lower()

def require_admin(request: Request):
    """Require admin access - redirect if not admin"""
    if not is_admin(request):
        return HTMLResponse("""
            <h1>Access Denied</h1>
            <p>You do not have permission to access this page.</p>
            <p><a href="/">← Back to Dashboard</a></p>
        """)
    return None

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
                <h2>💳 Billing & Credits</h2>
                <p>View your credits, top-up your account, and see usage history.</p>
                <a href="/billing" class="tool-btn">View Billing</a>
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

# --- Ping endpoint ---
@app.get("/api/ping")
def ping():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
