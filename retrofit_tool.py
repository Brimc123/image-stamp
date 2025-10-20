from fastapi import FastAPI, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List

# Import our modules
from database import init_db, get_user_by_id
from auth import (
    get_login_page, post_login,
    get_signup_page, post_signup,
    logout, require_active_user_row,
    is_admin
)
from billing import (
    get_billing_page,
    get_topup_page,
    post_topup
)
from admin import (
    get_admin_panel,
    toggle_user_status,
    toggle_timestamp_access,
    toggle_retrofit_access,
    get_admin_billing
)
from timestamp_tool import (
    get_timestamp_tool_page,
    post_timestamp_tool
)
from retrofit_tool import (
    get_retrofit_tool_page,
    get_calc_upload_page,
    get_retrofit_questions_page
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

    # CRITICAL: Get FRESH user data from database (session has old data!)
    try:
        user_id = user_row["id"]
        fresh_user = get_user_by_id(user_id)
        if fresh_user:
            user_row = fresh_user
    except Exception:
        pass
    
    # Get credits from database
    try:
        credits = float(user_row.get("credits", 0.0))
    except Exception:
        credits = 0.0

    try:
        has_timestamp_access = user_row.get("timestamp_tool_access", 1) == 1
    except Exception:
        has_timestamp_access = True

    try:
        has_retrofit_access = user_row.get("retrofit_tool_access", 1) == 1
    except Exception:
        has_retrofit_access = True

    user_is_admin = is_admin(request)

    admin_card_html = """
            <div class="tool-card admin-card">
                <h2>Admin Panel</h2>
                <p>Manage users, suspensions, and view all billing.</p>
                <a href="/admin" class="tool-button">Open Admin</a>
            </div>
    """ if user_is_admin else ""

    timestamp_card = f"""
        <div class="tool-card {'disabled-card' if not has_timestamp_access else ''}">
            <h2>Timestamp Tool</h2>
            <p>Add timestamps to multiple images with custom date ranges and cropping options.</p>
            {('<a href="/tool/timestamp" class="tool-button">Open Tool</a>') if has_timestamp_access else '<span class="disabled-text">Access Suspended</span>'}
        </div>
    """

    retrofit_card = f"""
        <div class="tool-card {'disabled-card' if not has_retrofit_access else ''}">
            <h2>Retrofit Design Tool</h2>
            <p>Generate PAS 2035 compliant retrofit designs with automated questioning.</p>
            {('<a href="/tool/retrofit" class="tool-button">Open Tool</a>') if has_retrofit_access else '<span class="disabled-text">Access Suspended</span>'}
        </div>
    """

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
        .tool-button:hover {{ transform: scale(1.05); }}
        .admin-card {{
            border: 3px solid #f39c12;
            background: linear-gradient(135deg, #fff9e6 0%, #ffe6cc 100%);
        }}
        .disabled-card {{ opacity: 0.5; background: #f5f5f5; }}
        .disabled-text {{ color: #e74c3c; font-weight: 600; }}
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

# ==================== BILLING ROUTES ====================

@app.get("/billing")
def billing_page(request: Request):
    return get_billing_page(request)

@app.get("/topup")
def topup_page(request: Request):
    return get_topup_page(request)

@app.post("/topup")
def topup(request: Request, amount: float = Form(...)):
    return post_topup(request, amount)

# ==================== ADMIN ROUTES ====================

@app.get("/admin")
def admin_page(request: Request):
    return get_admin_panel(request)

@app.post("/admin/toggle-status")
def admin_toggle_status(request: Request, user_id: int = Form(...), current_status: str = Form(...)):
    return toggle_user_status(request, user_id, current_status)

@app.post("/admin/toggle-timestamp")
def admin_toggle_timestamp(request: Request, user_id: int = Form(...), current_access: str = Form(...)):
    return toggle_timestamp_access(request, user_id, current_access)

@app.post("/admin/toggle-retrofit")
def admin_toggle_retrofit(request: Request, user_id: int = Form(...), current_access: str = Form(...)):
    return toggle_retrofit_access(request, user_id, current_access)

@app.get("/admin/billing")
def admin_billing_page(request: Request):
    return get_admin_billing(request)

# ==================== TIMESTAMP TOOL ROUTES ====================

@app.get("/tool/timestamp")
def timestamp_tool_page(request: Request):
    return get_timestamp_tool_page(request)

@app.post("/api/process-timestamp")
async def process_timestamp(request: Request):
    return await post_timestamp_tool(request)

# ==================== RETROFIT TOOL ROUTES ====================

@app.get("/tool/retrofit")
def retrofit_tool_page(request: Request):
    """Phase 1: Upload page"""
    return get_retrofit_tool_page()

@app.post("/api/retrofit-process")
async def process_retrofit_files(request: Request):
    """Process Phase 1 uploads"""
    return await post_retrofit_process(request)

@app.get("/tool/retrofit/calcs")
def retrofit_calc_upload(request: Request):
    """Phase 2: Calc upload page"""
    from retrofit_tool import get_session_data
    session_data = get_session_data(1)  # Get user_id from session in production
    return get_calc_upload_page(session_data)

@app.post("/api/retrofit-calcs")
async def process_retrofit_calcs(request: Request):
    """Process Phase 2 calc uploads"""
    return await post_retrofit_calcs(request)

@app.get("/tool/retrofit/questions")
def retrofit_questions(request: Request):
    """Phase 3: Questions page"""
    from retrofit_tool import get_session_data
    session_data = get_session_data(1)
    return get_retrofit_questions_page(session_data)

@app.post("/api/retrofit-answer")
async def save_retrofit_answer(request: Request):
    """Process Phase 3 answers"""
    return await post_retrofit_answer(request)

@app.get("/tool/retrofit/review")
def retrofit_review(request: Request):
    """Phase 4: Review page"""
    from retrofit_tool import get_session_data, get_retrofit_review_page
    session_data = get_session_data(1)
    return get_retrofit_review_page(session_data)

# ==================== HEALTH CHECK ====================

@app.get("/api/ping")
def ping():
    """Health check for Render"""
    return {"status": "ok"}

# ==================== RUN SERVER ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
