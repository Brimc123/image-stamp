from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

# Import our modules
from database import init_db
from auth import (
    get_login_page, post_login,
    get_signup_page, post_signup,
    logout, require_active_user_row,
    is_admin
)

# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database on startup
init_db()

# ==================== AUTH ROUTES ====================

@app.get("/login")
def login_page():
    return get_login_page()

@app.post("/login")
def login(email: str = Form(...), password: str = Form(...)):
    return post_login(email, password)

@app.get("/signup")
def signup_page():
    return get_signup_page()

@app.post("/signup")
def signup(email: str = Form(...), password: str = Form(...)):
    return post_signup(email, password)

@app.get("/logout")
def logout_route():
    return logout()

# ==================== DASHBOARD ====================

@app.get("/")
async def root(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    email = user_row["email"]
    user_is_admin = is_admin(request)
    
    try:
        credits = user_row["credits"]
    except (KeyError, TypeError):
        credits = 0.0
    
    try:
        has_timestamp_access = user_row["timestamp_tool_access"] == 1
    except (KeyError, TypeError):
        has_timestamp_access = True
    
    try:
        has_retrofit_access = user_row["retrofit_tool_access"] == 1
    except (KeyError, TypeError):
        has_retrofit_access = True
    
    # Admin card (only show to admin)
    admin_card_html = ""
    if user_is_admin:
        admin_card_html = """
            <div class="tool-card admin-card">
                <h2>Admin Panel</h2>
                <p>Manage users, suspensions, and view all billing.</p>
                <a href="/admin" class="tool-button">Open Admin</a>
            </div>
        """
    
    # Timestamp tool card
    timestamp_card = f"""
        <div class="tool-card {'disabled-card' if not has_timestamp_access else ''}">
            <h2>Timestamp Tool</h2>
            <p>Add timestamps to multiple images with custom date ranges and cropping options.</p>
            {'<a href="/tool/timestamp" class="tool-button">Open Tool</a>' if has_timestamp_access else '<span class="disabled-text">Access Suspended</span>'}
        </div>
    """
    
    # Retrofit tool card
    retrofit_card = f"""
        <div class="tool-card {'disabled-card' if not has_retrofit_access else ''}">
            <h2>Retrofit Design Tool</h2>
            <p>Generate PAS 2035 compliant retrofit designs with automated questioning.</p>
            {'<a href="/tool/retrofit" class="tool-button">Open Tool</a>' if has_retrofit_access else '<span class="disabled-text">Access Suspended</span>'}
        </div>
    """
    
    # Billing card
    billing_card_html = """
        <div class="tool-card">
            <h2>Billing & Credits</h2>
            <p>Manage your account credits and view transaction history.</p>
            <a href="/billing" class="tool-button">View Billing</a>
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
        <h1>AutoDate Dashboard</h1>
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

# ==================== PLACEHOLDER ROUTES ====================

@app.get("/billing")
def billing_placeholder(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head><title>Billing - Coming Soon</title></head>
        <body>
            <h1>Billing Page - Coming in Phase 2</h1>
            <a href="/">Back to Dashboard</a>
        </body>
        </html>
    """)

@app.get("/admin")
def admin_placeholder(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    if not is_admin(request):
        return HTMLResponse("<h1>Access Denied</h1><a href='/'>Back</a>")
    
    return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head><title>Admin - Coming Soon</title></head>
        <body>
            <h1>Admin Panel - Coming in Phase 2</h1>
            <a href="/">Back to Dashboard</a>
        </body>
        </html>
    """)

@app.get("/tool/timestamp")
def timestamp_placeholder(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head><title>Timestamp Tool - Coming Soon</title></head>
        <body>
            <h1>Timestamp Tool - Coming in Phase 3</h1>
            <a href="/">Back to Dashboard</a>
        </body>
        </html>
    """)

@app.get("/tool/retrofit")
def retrofit_placeholder(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head><title>Retrofit Tool - Coming Soon</title></head>
        <body>
            <h1>Retrofit Tool - Coming in Phase 4</h1>
            <a href="/">Back to Dashboard</a>
        </body>
        </html>
    """)

# ==================== HEALTH CHECK ====================

@app.get("/api/ping")
def ping():
    """Health check for Render"""
    return {"status": "ok"}

# ==================== RUN SERVER ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
