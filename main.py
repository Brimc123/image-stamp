"""
AutoDate Main Application - COMPLETE WORKING VERSION
All routes, admin panel, login, tools integrated
FIXED: Retrofit tool routes no longer double-wrap HTMLResponse
"""

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# Import modules
from auth import (
    get_login_page, post_login, post_logout, get_register_page, 
    post_register, require_active_user_row
)
from database import (
    get_all_users, update_user_status, update_user_credits,
    get_user_transactions, add_transaction
)
from admin import get_admin_page, post_admin_update_user
from timestamp_tool import get_timestamp_tool_page, post_timestamp_tool
from retrofit_tool import (
    get_retrofit_tool_page, post_retrofit_process,
    get_calc_upload_page, post_calc_upload,
    get_questions_page, post_questions_submit,
    get_pdf_download
)

# Initialize FastAPI
app = FastAPI(title="AutoDate Platform")

# ==================== HEALTH CHECK ====================

@app.get("/api/ping")
def health_check():
    """Health check endpoint for Render"""
    return {"status": "ok"}

# ==================== HOMEPAGE ====================

@app.get("/", response_class=HTMLResponse)
def homepage(request: Request):
    """Main dashboard with tool cards"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    username = user_row.get("username", "User")
    credits = float(user_row.get("credits", 0.0))
    is_admin = user_row.get("is_admin", 0) == 1
    
    admin_link = '<a href="/admin" class="nav-link">👑 Admin Panel</a>' if is_admin else ''
    
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoDate - Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 2rem;
        }}
        
        .navbar {{
            background: rgba(255,255,255,0.95);
            padding: 1rem 2rem;
            border-radius: 15px;
            margin-bottom: 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        
        .nav-left {{ display: flex; align-items: center; gap: 2rem; }}
        .logo {{ font-size: 1.5rem; font-weight: 800; color: #667eea; }}
        .nav-link {{ 
            text-decoration: none; 
            color: #4a5568; 
            font-weight: 600;
            transition: color 0.3s;
        }}
        .nav-link:hover {{ color: #667eea; }}
        
        .user-info {{
            display: flex;
            align-items: center;
            gap: 1.5rem;
        }}
        
        .credits {{
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            color: white;
            padding: 0.5rem 1.5rem;
            border-radius: 25px;
            font-weight: 600;
            font-size: 0.9rem;
        }}
        
        .username {{
            font-weight: 600;
            color: #1f2937;
        }}
        
        .logout-btn {{
            background: #ef4444;
            color: white;
            border: none;
            padding: 0.5rem 1.5rem;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s;
        }}
        .logout-btn:hover {{ background: #dc2626; transform: translateY(-2px); }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        
        .welcome {{
            background: rgba(255,255,255,0.95);
            padding: 2rem;
            border-radius: 15px;
            margin-bottom: 2rem;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        
        .welcome h1 {{
            font-size: 2.5rem;
            color: #1f2937;
            margin-bottom: 0.5rem;
        }}
        
        .welcome p {{
            color: #6b7280;
            font-size: 1.1rem;
        }}
        
        .tools-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 2rem;
        }}
        
        .tool-card {{
            background: rgba(255,255,255,0.95);
            border-radius: 20px;
            padding: 2.5rem;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            transition: all 0.3s;
            cursor: pointer;
            text-decoration: none;
            color: inherit;
            display: block;
        }}
        
        .tool-card:hover {{
            transform: translateY(-10px);
            box-shadow: 0 20px 40px rgba(0,0,0,0.3);
        }}
        
        .tool-icon {{
            font-size: 4rem;
            margin-bottom: 1rem;
            display: block;
        }}
        
        .tool-title {{
            font-size: 1.8rem;
            font-weight: 700;
            color: #1f2937;
            margin-bottom: 0.5rem;
        }}
        
        .tool-description {{
            color: #6b7280;
            font-size: 1rem;
            line-height: 1.6;
            margin-bottom: 1rem;
        }}
        
        .tool-cost {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 0.5rem 1rem;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.9rem;
        }}
        
        .tool-badge {{
            display: inline-block;
            background: #10b981;
            color: white;
            padding: 0.3rem 0.8rem;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 700;
            margin-left: 0.5rem;
        }}
        
        @media (max-width: 768px) {{
            .tools-grid {{ grid-template-columns: 1fr; }}
            .navbar {{ flex-direction: column; gap: 1rem; }}
            .nav-left {{ flex-direction: column; }}
        }}
    </style>
</head>
<body>
    <div class="navbar">
        <div class="nav-left">
            <div class="logo">🤖 AutoDate</div>
            <a href="/" class="nav-link">🏠 Dashboard</a>
            {admin_link}
        </div>
        <div class="user-info">
            <div class="username">👤 {username}</div>
            <div class="credits">💳 £{credits:.2f}</div>
            <form method="POST" action="/logout" style="margin: 0;">
                <button type="submit" class="logout-btn">Logout</button>
            </form>
        </div>
    </div>

    <div class="container">
        <div class="welcome">
            <h1>Welcome back, {username}! 👋</h1>
            <p>Choose a tool to get started with your project automation</p>
        </div>

        <div class="tools-grid">
            <a href="/tool/timestamp" class="tool-card">
                <span class="tool-icon">⏱️</span>
                <div class="tool-title">Timestamp Tool</div>
                <div class="tool-description">
                    Generate professional timestamp documents from PDF schedules. 
                    Perfect for construction projects and site management.
                </div>
                <span class="tool-cost">💰 £5.00 per use</span>
            </a>

            <a href="/tool/retrofit" class="tool-card">
                <span class="tool-icon">🏗️</span>
                <div class="tool-title">Retrofit Design Tool</div>
                <div class="tool-description">
                    Create PAS 2035 compliant retrofit design documents. 
                    Extract data from site notes, condition reports, and calculations.
                </div>
                <span class="tool-cost">💰 £10.00 per use</span>
                <span class="tool-badge">NEW</span>
            </a>
        </div>
    </div>
</body>
</html>
    """
    return HTMLResponse(html)


# ==================== AUTH ROUTES ====================

@app.get("/login", response_class=HTMLResponse)
def route_get_login(request: Request):
    return get_login_page(request)

@app.post("/login")
async def route_post_login(request: Request, username: str = Form(...), password: str = Form(...)):
    return await post_login(request, username, password)

@app.post("/logout")
def route_post_logout(request: Request):
    return post_logout(request)

@app.get("/register", response_class=HTMLResponse)
def route_get_register(request: Request):
    return get_register_page(request)

@app.post("/register")
async def route_post_register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...)
):
    return await post_register(request, username, password, confirm_password)


# ==================== ADMIN ROUTES ====================

@app.get("/admin", response_class=HTMLResponse)
def route_get_admin(request: Request):
    return get_admin_page(request)

@app.post("/admin/update-user")
async def route_post_admin_update(
    request: Request,
    user_id: int = Form(...),
    action: str = Form(...),
    credits: float = Form(None)
):
    return await post_admin_update_user(request, user_id, action, credits)


# ==================== TIMESTAMP TOOL ROUTES ====================

@app.get("/tool/timestamp", response_class=HTMLResponse)
def route_timestamp_tool(request: Request):
    return get_timestamp_tool_page(request)

@app.post("/api/process-timestamp")
async def route_timestamp_process(request: Request):
    return await post_timestamp_tool(request)


# ==================== RETROFIT TOOL ROUTES - FIXED ====================

@app.get("/tool/retrofit")
def route_retrofit_tool(request: Request):
    """FIXED: Function already returns HTMLResponse, don't wrap again"""
    return get_retrofit_tool_page(request)

@app.post("/tool/retrofit/process")
async def route_retrofit_process(request: Request):
    """FIXED: Changed route to match what the form expects"""
    return await post_retrofit_process(request)

@app.get("/tool/retrofit/calcs")
def route_retrofit_calcs(request: Request):
    """FIXED: Function already returns HTMLResponse"""
    return get_calc_upload_page(request)

@app.post("/tool/retrofit/calcs")
async def route_retrofit_calcs_upload(request: Request):
    """FIXED: Changed route to match what the form expects"""
    return await post_calc_upload(request)

@app.get("/tool/retrofit/questions")
def route_retrofit_questions(request: Request):
    """FIXED: Function already returns HTMLResponse"""
    return get_questions_page(request)

@app.post("/tool/retrofit/answer")
async def route_retrofit_questions_submit(request: Request):
    """FIXED: Changed route to match what the form expects"""
    return await post_questions_submit(request)

@app.get("/tool/retrofit/download")
def route_retrofit_pdf(request: Request):
    """FIXED: Changed route to match expectations"""
    return get_pdf_download(request)


# ==================== RUN SERVER ====================

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
