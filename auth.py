"""
Authentication Module - CORRECT VERSION
This defines all auth functions that main.py imports
"""

from fastapi import Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from database import get_user_by_username, create_user, get_user_by_id
import hashlib

# =============================================================================
# SESSION HELPERS
# =============================================================================

def get_session_user_id(request: Request) -> int:
    """Get user ID from session cookie"""
    user_id = request.cookies.get("user_id")
    return int(user_id) if user_id else None


def hash_password(password: str) -> str:
    """Hash password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()


# =============================================================================
# AUTH GUARDS
# =============================================================================

def require_active_user_row(request: Request):
    """Require logged-in active user, return user row or redirect"""
    user_id = get_session_user_id(request)
    if not user_id:
        return RedirectResponse("/login", status_code=303)
    
    user_row = get_user_by_id(user_id)
    if not user_row:
        return RedirectResponse("/login", status_code=303)
    
    if not user_row.get("is_active", 0):
        return HTMLResponse("<h1>Account Disabled</h1><p>Your account has been disabled. Please contact support.</p>")
    
    return user_row


def require_admin(request: Request):
    """Require admin user, return user row or redirect"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    if not user_row.get("is_admin", 0):
        return HTMLResponse("<h1>Access Denied</h1><p>Admin access required.</p>")
    
    return user_row


# =============================================================================
# PAGE RENDERERS
# =============================================================================

def get_login_page(request: Request):
    """Render login page"""
    error = request.query_params.get("error", "")
    error_html = f'<div style="color: #ef4444; background: #fee2e2; padding: 12px; border-radius: 8px; margin-bottom: 20px;">{error}</div>' if error else ""
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login - AutoDate</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}
            .login-box {{
                background: white;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                width: 100%;
                max-width: 400px;
            }}
            h1 {{ font-size: 28px; margin-bottom: 24px; text-align: center; color: #1a202c; }}
            .form-group {{ margin-bottom: 20px; }}
            label {{ display: block; margin-bottom: 8px; font-weight: 600; color: #2d3748; }}
            input {{
                width: 100%;
                padding: 12px;
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                font-size: 16px;
            }}
            input:focus {{ outline: none; border-color: #667eea; }}
            button {{
                width: 100%;
                padding: 14px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
            }}
            button:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4); }}
            .register-link {{ text-align: center; margin-top: 20px; color: #4a5568; }}
            .register-link a {{ color: #667eea; font-weight: 600; text-decoration: none; }}
        </style>
    </head>
    <body>
        <div class="login-box">
            <h1>🔐 Login</h1>
            {error_html}
            <form method="POST" action="/login">
                <div class="form-group">
                    <label>Email</label>
                    <input type="email" name="username" required>
                </div>
                <div class="form-group">
                    <label>Password</label>
                    <input type="password" name="password" required>
                </div>
                <button type="submit">Login</button>
            </form>
            <div class="register-link">
                Don't have an account? <a href="/register">Register here</a>
            </div>
        </div>
    </body>
    </html>
    """)


def get_register_page():
    """Render registration page"""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Register - AutoDate</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }
            .register-box {
                background: white;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                width: 100%;
                max-width: 400px;
            }
            h1 { font-size: 28px; margin-bottom: 24px; text-align: center; color: #1a202c; }
            .form-group { margin-bottom: 20px; }
            label { display: block; margin-bottom: 8px; font-weight: 600; color: #2d3748; }
            input {
                width: 100%;
                padding: 12px;
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                font-size: 16px;
            }
            input:focus { outline: none; border-color: #667eea; }
            button {
                width: 100%;
                padding: 14px;
                background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
            }
            button:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(16, 185, 129, 0.4); }
            .login-link { text-align: center; margin-top: 20px; color: #4a5568; }
            .login-link a { color: #667eea; font-weight: 600; text-decoration: none; }
        </style>
    </head>
    <body>
        <div class="register-box">
            <h1>✨ Create Account</h1>
            <form method="POST" action="/register">
                <div class="form-group">
                    <label>Email</label>
                    <input type="email" name="username" required>
                </div>
                <div class="form-group">
                    <label>Password</label>
                    <input type="password" name="password" required>
                </div>
                <button type="submit">Create Account</button>
            </form>
            <div class="login-link">
                Already have an account? <a href="/login">Login here</a>
            </div>
        </div>
    </body>
    </html>
    """)


# =============================================================================
# FORM HANDLERS
# =============================================================================

async def post_login(request: Request):
    """Handle login form submission"""
    form = await request.form()
    username = form.get("username")
    password = form.get("password")
    
    user_row = get_user_by_username(username)
    if not user_row:
        return RedirectResponse("/login?error=Invalid credentials", status_code=303)
    
    password_hash = hash_password(password)
    if user_row["password_hash"] != password_hash:
        return RedirectResponse("/login?error=Invalid credentials", status_code=303)
    
    if not user_row.get("is_active", 0):
        return RedirectResponse("/login?error=Account disabled", status_code=303)
    
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(key="user_id", value=str(user_row["id"]), httponly=True)
    return response


async def post_register(request: Request):
    """Handle registration form submission"""
    form = await request.form()
    username = form.get("username")
    password = form.get("password")
    
    existing_user = get_user_by_username(username)
    if existing_user:
        return HTMLResponse("<h1>Error</h1><p>User already exists. <a href='/register'>Try again</a></p>")
    
    password_hash = hash_password(password)
    user_id = create_user(username, password_hash)
    
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(key="user_id", value=str(user_id), httponly=True)
    return response


def post_logout(request: Request):
    """Handle logout"""
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("user_id")
    return response
