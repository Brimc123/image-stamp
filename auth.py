"""
Authentication Module - COMPLETE WORKING VERSION
Handles login, logout, registration, and session management
"""

import hashlib
import secrets
from typing import Optional, Dict
from fastapi import Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

# Import database functions
from database import get_user_by_username, create_user, get_user_by_id

# In-memory session storage (replace with Redis in production)
SESSIONS = {}

# ==================== SESSION MANAGEMENT ====================

def create_session(user_id: int) -> str:
    """Create a new session token"""
    session_token = secrets.token_urlsafe(32)
    SESSIONS[session_token] = user_id
    return session_token


def get_user_from_session(session_token: str) -> Optional[int]:
    """Get user ID from session token"""
    return SESSIONS.get(session_token)


def delete_session(session_token: str):
    """Delete a session"""
    if session_token in SESSIONS:
        del SESSIONS[session_token]


# ==================== PASSWORD HASHING ====================

def hash_password(password: str) -> str:
    """Hash a password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()


# ==================== AUTH HELPERS ====================

def get_current_user_row(request: Request) -> Optional[Dict]:
    """Get current user from session cookie"""
    session_token = request.cookies.get("session_token")
    if not session_token:
        return None
    
    user_id = get_user_from_session(session_token)
    if not user_id:
        return None
    
    return get_user_by_id(user_id)


def is_admin(request: Request) -> bool:
    """Check if current user is an admin"""
    user_row = get_current_user_row(request)
    if not user_row:
        return False
    return user_row.get("is_admin", 0) == 1


def require_admin(request: Request):
    """Require admin access, redirect if not admin"""
    user_row = get_current_user_row(request)
    
    if not user_row:
        return RedirectResponse(url="/login", status_code=303)
    
    if user_row.get("is_admin", 0) != 1:
        return HTMLResponse("""
            <html>
            <head>
                <title>Access Denied</title>
                <style>
                    body {
                        font-family: sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .error-box {
                        background: white;
                        padding: 3rem;
                        border-radius: 20px;
                        text-align: center;
                    }
                </style>
            </head>
            <body>
                <div class="error-box">
                    <h1>🚫 Access Denied</h1>
                    <p>You need administrator privileges to access this page.</p>
                    <a href="/">Back to Dashboard</a>
                </div>
            </body>
            </html>
        """)
    
    return user_row


def require_active_user_row(request: Request):
    """Require an active user, redirect to login if not authenticated"""
    user_row = get_current_user_row(request)
    
    if not user_row:
        return RedirectResponse(url="/login", status_code=303)
    
    # Check if user is active
    if user_row.get("is_active", 1) != 1:
        return HTMLResponse("""
            <html>
            <head>
                <title>Account Suspended</title>
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        margin: 0;
                        padding: 20px;
                    }
                    .container {
                        background: white;
                        padding: 3rem;
                        border-radius: 20px;
                        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                        text-align: center;
                        max-width: 500px;
                    }
                    h1 {
                        color: #ef4444;
                        margin-bottom: 1rem;
                        font-size: 2rem;
                    }
                    p {
                        color: #6b7280;
                        line-height: 1.6;
                        margin-bottom: 2rem;
                    }
                    .logout-btn {
                        background: #ef4444;
                        color: white;
                        border: none;
                        padding: 1rem 2rem;
                        border-radius: 8px;
                        cursor: pointer;
                        font-weight: 600;
                        font-size: 1rem;
                        text-decoration: none;
                        display: inline-block;
                    }
                    .logout-btn:hover {
                        background: #dc2626;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>⚠️ Account Suspended</h1>
                    <p>Your account has been suspended by an administrator. Please contact support for more information.</p>
                    <form method="POST" action="/logout">
                        <button type="submit" class="logout-btn">Logout</button>
                    </form>
                </div>
            </body>
            </html>
        """)
    
    return user_row


# ==================== LOGIN PAGE ====================

def get_login_page(request: Request):
    """Display login page"""
    # If already logged in, redirect to homepage
    user_row = get_current_user_row(request)
    if user_row:
        return RedirectResponse(url="/", status_code=303)
    
    html = """
<!DOCTYPE html>
<html lang="en">
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
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        
        .login-container {
            background: white;
            padding: 3rem;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            width: 100%;
            max-width: 450px;
        }
        
        .logo {
            text-align: center;
            font-size: 3rem;
            margin-bottom: 1rem;
        }
        
        h1 {
            text-align: center;
            color: #1f2937;
            margin-bottom: 0.5rem;
            font-size: 2rem;
        }
        
        .subtitle {
            text-align: center;
            color: #6b7280;
            margin-bottom: 2rem;
        }
        
        .form-group {
            margin-bottom: 1.5rem;
        }
        
        label {
            display: block;
            color: #374151;
            font-weight: 600;
            margin-bottom: 0.5rem;
        }
        
        input {
            width: 100%;
            padding: 0.75rem;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            font-size: 1rem;
            transition: border-color 0.3s;
        }
        
        input:focus {
            outline: none;
            border-color: #667eea;
        }
        
        .login-btn {
            width: 100%;
            padding: 1rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.3s, box-shadow 0.3s;
        }
        
        .login-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4);
        }
        
        .register-link {
            text-align: center;
            margin-top: 1.5rem;
            color: #6b7280;
        }
        
        .register-link a {
            color: #667eea;
            text-decoration: none;
            font-weight: 600;
        }
        
        .register-link a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="logo">🤖</div>
        <h1>Welcome Back</h1>
        <p class="subtitle">Sign in to AutoDate</p>
        
        <form method="POST" action="/login">
            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" required autofocus>
            </div>
            
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required>
            </div>
            
            <button type="submit" class="login-btn">Sign In</button>
        </form>
        
        <div class="register-link">
            Don't have an account? <a href="/register">Create one</a>
        </div>
    </div>
</body>
</html>
    """
    return HTMLResponse(html)


# ==================== LOGIN POST ====================

async def post_login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Handle login form submission"""
    # Get user from database
    user = get_user_by_username(username)
    
    if not user:
        return HTMLResponse("""
            <html>
            <head>
                <meta http-equiv="refresh" content="2;url=/login">
                <style>
                    body {
                        font-family: sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .error-box {
                        background: white;
                        padding: 2rem;
                        border-radius: 12px;
                        text-align: center;
                    }
                </style>
            </head>
            <body>
                <div class="error-box">
                    <h2>❌ Invalid Credentials</h2>
                    <p>Redirecting back to login...</p>
                </div>
            </body>
            </html>
        """)
    
    # Check password
    password_hash = hash_password(password)
    if user["password_hash"] != password_hash:
        return HTMLResponse("""
            <html>
            <head>
                <meta http-equiv="refresh" content="2;url=/login">
                <style>
                    body {
                        font-family: sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .error-box {
                        background: white;
                        padding: 2rem;
                        border-radius: 12px;
                        text-align: center;
                    }
                </style>
            </head>
            <body>
                <div class="error-box">
                    <h2>❌ Invalid Credentials</h2>
                    <p>Redirecting back to login...</p>
                </div>
            </body>
            </html>
        """)
    
    # Check if user is active
    if user.get("is_active", 1) != 1:
        return HTMLResponse("""
            <html>
            <head>
                <meta http-equiv="refresh" content="3;url=/login">
                <style>
                    body {
                        font-family: sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .error-box {
                        background: white;
                        padding: 2rem;
                        border-radius: 12px;
                        text-align: center;
                    }
                </style>
            </head>
            <body>
                <div class="error-box">
                    <h2>⚠️ Account Suspended</h2>
                    <p>Your account has been suspended. Please contact support.</p>
                </div>
            </body>
            </html>
        """)
    
    # Create session
    session_token = create_session(user["id"])
    
    # Redirect to homepage with session cookie
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        max_age=86400 * 30  # 30 days
    )
    
    return response


# ==================== LOGOUT ====================

def post_logout(request: Request):
    """Handle logout - clear session cookie"""
    session_token = request.cookies.get("session_token")
    if session_token:
        delete_session(session_token)
    
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session_token")
    return response


# ==================== REGISTER PAGE ====================

def get_register_page(request: Request):
    """Display registration page"""
    # If already logged in, redirect to homepage
    user_row = get_current_user_row(request)
    if user_row:
        return RedirectResponse(url="/", status_code=303)
    
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Register - AutoDate</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        
        .register-container {
            background: white;
            padding: 3rem;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            width: 100%;
            max-width: 450px;
        }
        
        .logo {
            text-align: center;
            font-size: 3rem;
            margin-bottom: 1rem;
        }
        
        h1 {
            text-align: center;
            color: #1f2937;
            margin-bottom: 0.5rem;
            font-size: 2rem;
        }
        
        .subtitle {
            text-align: center;
            color: #6b7280;
            margin-bottom: 2rem;
        }
        
        .form-group {
            margin-bottom: 1.5rem;
        }
        
        label {
            display: block;
            color: #374151;
            font-weight: 600;
            margin-bottom: 0.5rem;
        }
        
        input {
            width: 100%;
            padding: 0.75rem;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            font-size: 1rem;
            transition: border-color 0.3s;
        }
        
        input:focus {
            outline: none;
            border-color: #667eea;
        }
        
        .register-btn {
            width: 100%;
            padding: 1rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.3s, box-shadow 0.3s;
        }
        
        .register-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4);
        }
        
        .login-link {
            text-align: center;
            margin-top: 1.5rem;
            color: #6b7280;
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
    <div class="register-container">
        <div class="logo">🤖</div>
        <h1>Create Account</h1>
        <p class="subtitle">Join AutoDate today</p>
        
        <form method="POST" action="/register">
            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" required autofocus>
            </div>
            
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required>
            </div>
            
            <div class="form-group">
                <label for="confirm_password">Confirm Password</label>
                <input type="password" id="confirm_password" name="confirm_password" required>
            </div>
            
            <button type="submit" class="register-btn">Create Account</button>
        </form>
        
        <div class="login-link">
            Already have an account? <a href="/login">Sign in</a>
        </div>
    </div>
</body>
</html>
    """
    return HTMLResponse(html)


# ==================== REGISTER POST ====================

async def post_register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...)
):
    """Handle registration form submission"""
    
    # Check if passwords match
    if password != confirm_password:
        return HTMLResponse("""
            <html>
            <head>
                <meta http-equiv="refresh" content="2;url=/register">
                <style>
                    body {
                        font-family: sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .error-box {
                        background: white;
                        padding: 2rem;
                        border-radius: 12px;
                        text-align: center;
                    }
                </style>
            </head>
            <body>
                <div class="error-box">
                    <h2>❌ Passwords Don't Match</h2>
                    <p>Redirecting back to registration...</p>
                </div>
            </body>
            </html>
        """)
    
    # Check if username already exists
    existing_user = get_user_by_username(username)
    if existing_user:
        return HTMLResponse("""
            <html>
            <head>
                <meta http-equiv="refresh" content="2;url=/register">
                <style>
                    body {
                        font-family: sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .error-box {
                        background: white;
                        padding: 2rem;
                        border-radius: 12px;
                        text-align: center;
                    }
                </style>
            </head>
            <body>
                <div class="error-box">
                    <h2>❌ Username Already Exists</h2>
                    <p>Please choose a different username...</p>
                </div>
            </body>
            </html>
        """)
    
    # Create user
    password_hash = hash_password(password)
    user_id = create_user(username, password_hash)
    
    # Create session
    session_token = create_session(user_id)
    
    # Redirect to homepage with session cookie
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        max_age=86400 * 30  # 30 days
    )
    
    return response
