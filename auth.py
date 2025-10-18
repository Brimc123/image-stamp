from fastapi import Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from database import get_user_by_email, create_user
from config import ADMIN_EMAIL

def is_admin(request: Request) -> bool:
    """Check if user is admin"""
    email = request.cookies.get("user_email")
    return email == ADMIN_EMAIL

def set_cookie(response: Response, key: str, value: str):
    """Set cookie"""
    response.set_cookie(key=key, value=value, httponly=True, samesite="lax")

def delete_cookie(response: Response, key: str):
    """Delete cookie"""
    response.delete_cookie(key=key)

def require_active_user_row(request: Request):
    """Check if user is logged in and active"""
    email = request.cookies.get("user_email")
    if not email:
        return RedirectResponse(url="/login", status_code=302)
    
    user_row = get_user_by_email(email)
    if not user_row:
        return RedirectResponse(url="/login", status_code=302)
    
    # Check if account is suspended (but not admin)
    try:
        is_active = user_row["is_active"]
    except (KeyError, TypeError):
        is_active = 1
    
    if is_active == 0 and email != ADMIN_EMAIL:
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
                    <h1>Account Suspended</h1>
                    <p>Your account has been suspended. Please contact the administrator for assistance.</p>
                    <a href="/logout">Logout</a>
                </div>
            </body>
            </html>
        """)
    
    return user_row

# Login page HTML
LOGIN_HTML = """
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
        <h1>Login to AutoDate</h1>
        <form method="POST" action="/login">
            <div class="form-group">
                <label>Email</label>
                <input type="email" name="email" required placeholder="your@email.com">
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" required placeholder="Password">
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

# Signup page HTML
SIGNUP_HTML = """
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
        <h1>Create Account</h1>
        <form method="POST" action="/signup">
            <div class="form-group">
                <label>Email</label>
                <input type="email" name="email" required placeholder="your@email.com">
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" required placeholder="Password">
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

def get_login_page():
    """Return login page"""
    return HTMLResponse(LOGIN_HTML)

def post_login(email: str = Form(...), password: str = Form(...)):
    """Handle login"""
    user_row = get_user_by_email(email)
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

def get_signup_page():
    """Return signup page"""
    return HTMLResponse(SIGNUP_HTML)

def post_signup(email: str = Form(...), password: str = Form(...)):
    """Handle signup"""
    user_id = create_user(email, password)
    if not user_id:
        return HTMLResponse("""
            <script>
                alert("Email already exists!");
                window.location.href = "/signup";
            </script>
        """)
    resp = RedirectResponse(url="/", status_code=302)
    set_cookie(resp, "user_email", email)
    return resp

def logout():
    """Handle logout"""
    resp = RedirectResponse(url="/login", status_code=302)
    delete_cookie(resp, "user_email")
    return resp
