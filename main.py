"""
AutoDate Main Application - FINAL VERSION
Beautiful glassmorphism UI + All working routes from main (45).py
"""

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, Response
import uvicorn

# EXACT imports from working deployment
from auth import require_active_user_row, require_admin, get_login_page, get_register_page, post_login, post_register, post_logout
from database import get_user_by_id, get_all_users, update_user_status, set_user_credits, update_user_tool_access
from admin import get_admin_dashboard, get_admin_weekly_report, get_admin_user_edit, post_admin_user_edit

from billing import get_billing_page, get_topup_page, post_topup
from timestamp_tool import get_timestamp_tool_page, post_timestamp_tool
from retrofit_tool import get_retrofit_tool_page, post_retrofit_process
from ats_tool import ats_generator_route
from adf_tool import adf_checklist_route
from sf70_tool import sf70_tool_route

app = FastAPI()
from fastapi.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory="static"), name="static")

# Health check for Render
@app.get("/api/ping")
def ping():
    return {"status": "ok"}

# ============================================================================
# STUNNING DASHBOARD WITH GLASSMORPHISM
# ============================================================================

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    """Modern glassmorphism dashboard"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, RedirectResponse):
        return user_row
    
    username = user_row.get("username", "User")
    credits = float(user_row.get("credits", 0.0))
    is_admin = user_row.get("is_admin", 0) == 1
    
    # Get tool access for current user
    timestamp_access = user_row.get("timestamp_tool_access", 1) == 1
    retrofit_access = user_row.get("retrofit_tool_access", 1) == 1
    ats_access = user_row.get("ats_tool_access", 1) == 1
    adf_access = user_row.get("adf_tool_access", 1) == 1
    sf70_access = user_row.get("sf70_tool_access", 1) == 1

    # Build tool cards HTML based on access
    timestamp_card = f'''<a href="/tool/timestamp" class="tool-card">
                <span class="tool-icon">⏱️</span>
                <h2 class="tool-title">Timestamp Tool</h2>
                <p class="tool-description">
                    Generate professional timestamp documents from PDF schedules. Perfect for construction projects and site management. Add accurate date/time stamps to your images instantly.
                </p>
                <div class="tool-footer">
                    <span class="tool-price">💰 £5.00 per use</span>
                </div>
            </a>''' if timestamp_access else ''

    retrofit_card = f'''<a href="/tool/retrofit" class="tool-card">
                <span class="tool-icon">🏗️</span>
                <h2 class="tool-title">Retrofit Design Tool</h2>
                <p class="tool-description">
                    Create PAS 2035 compliant retrofit design documents. Extract data from site notes, condition reports, and calculations. Reduce design time from 2-4 hours to 12-18 minutes.
                </p>
                <div class="tool-footer">
                    <span class="tool-price">💰 £10.00 per use</span>
                    <span class="new-badge">✨ New</span>
                </div>
            </a>''' if retrofit_access else ''
    
    ats_card = f'''<a href="/tool/ats-generator" class="tool-card"> 
                <span class="tool-icon">🏠</span>
                <h2 class="tool-title">Airtightness Strategy Generator</h2>
                <p class="tool-description">
                    Generate PAS 2035 Annex 8.2.35 compliant Airtightness Strategy documents. Auto-extracts data from Condition Reports and creates professional ATS documents instantly.
                </p>
                <div class="tool-footer">
                    <span class="tool-price">💰 £10.00 per use</span>
                    <span class="new-badge">✨ New</span>
                </div>
            </a>''' if ats_access else ''
    
    adf_card = f'''<a href="/tool/adf-checklist" class="tool-card">
                <span class="tool-icon">📋</span>
                <h2 class="tool-title">ADF Table D1 Generator</h2>
                <p class="tool-description">
                    Generate Approved Document F Table D1 checklists from Condition Reports. Automatically extracts background ventilation, trickle vents, and extract fan data for compliance verification.
                </p>
                <div class="tool-footer">
                    <span class="tool-price">💰 £5.00 per use</span>
                    <span class="new-badge">✨ New</span>
                </div>
            </a>''' if adf_access else ''
   
    sf70_card = f'''<a href="/tool/sf70" class="tool-card">
                <span class="tool-icon">⚡</span>
                <h2 class="tool-title">SF70 EEM Assessment</h2>
                <p class="tool-description">
                    Generate PAS 2035 compliant SF70 Energy Efficiency Measures assessments. Upload condition reports, select retrofit measures, and produce professional Path A/B/C classification reports.
                </p>
                <div class="tool-footer">
                    <span class="tool-price">💰 £10.00 per use</span>
                    <span class="new-badge">✨ New</span>
                </div>
            </a>''' if sf70_access else ''


    
    admin_link = f'<a href="/admin" class="nav-link admin-link">👑 Admin</a>' if is_admin else ''
    
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoDate Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
            min-height: 100vh;
            position: relative;
            overflow-x: hidden;
        }}
        
        body::before {{
            content: '';
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: 
                radial-gradient(circle at 20% 50%, rgba(255, 255, 255, 0.1) 0%, transparent 50%),
                radial-gradient(circle at 80% 80%, rgba(255, 255, 255, 0.1) 0%, transparent 50%),
                radial-gradient(circle at 40% 20%, rgba(255, 255, 255, 0.1) 0%, transparent 50%);
            animation: float 20s ease-in-out infinite;
            pointer-events: none;
        }}
        
        @keyframes float {{
            0%, 100% {{ transform: translateY(0) rotate(0deg); }}
            50% {{ transform: translateY(-20px) rotate(5deg); }}
        }}
        
        .navbar {{
            background: rgba(255, 255, 255, 0.15);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            padding: 1.25rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 1000;
        }}
        
        .logo {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            color: white;
            font-size: 1.5rem;
            font-weight: 700;
            text-decoration: none;
            transition: transform 0.3s ease;
        }}
        
        .logo:hover {{ transform: scale(1.05); }}
        .logo-icon {{ font-size: 2rem; }}
        
        .nav-menu {{
            display: flex;
            align-items: center;
            gap: 1.5rem;
        }}
        
        .nav-link {{
            color: white;
            text-decoration: none;
            font-weight: 500;
            padding: 0.5rem 1rem;
            border-radius: 12px;
            transition: all 0.3s ease;
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }}
        
        .nav-link:hover {{
            background: rgba(255, 255, 255, 0.25);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }}
        
        .admin-link {{
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            border: none;
            font-weight: 600;
        }}
        
        .credits-badge {{
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            color: white;
            padding: 0.5rem 1.25rem;
            border-radius: 12px;
            font-weight: 700;
            font-size: 1.1rem;
            border: 2px solid rgba(255, 255, 255, 0.3);
            box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
            cursor: pointer;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
        }}
        
        .credits-badge:hover {{
            transform: translateY(-3px);
            box-shadow: 0 6px 20px rgba(16, 185, 129, 0.4);
        }}
        
        .logout-btn {{
            background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
            border: none;
            padding: 0.5rem 1.25rem;
            border-radius: 12px;
            color: white;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3);
        }}
        
        .logout-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(239, 68, 68, 0.4);
        }}
        
        .user-badge {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            background: rgba(255, 255, 255, 0.2);
            padding: 0.5rem 1rem;
            border-radius: 12px;
            color: white;
            font-weight: 500;
        }}
        
        .user-icon {{ font-size: 1.2rem; }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 3rem 2rem;
        }}
        
        .welcome-section {{
            background: rgba(255, 255, 255, 0.15);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 24px;
            padding: 3rem;
            text-align: center;
            margin-bottom: 3rem;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            animation: fadeInUp 0.6s ease;
        }}
        
        @keyframes fadeInUp {{
            from {{ opacity: 0; transform: translateY(30px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        .welcome-title {{
            color: white;
            font-size: 3rem;
            font-weight: 800;
            margin-bottom: 1rem;
            text-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }}
        
        .welcome-subtitle {{
            color: rgba(255, 255, 255, 0.95);
            font-size: 1.25rem;
            font-weight: 400;
        }}
        
        .wave {{
            display: inline-block;
            animation: wave 2s ease-in-out infinite;
        }}
        
        @keyframes wave {{
            0%, 100% {{ transform: rotate(0deg); }}
            25% {{ transform: rotate(20deg); }}
            75% {{ transform: rotate(-20deg); }}
        }}
        
        .tools-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(450px, 1fr));
            gap: 2rem;
            animation: fadeInUp 0.8s ease 0.2s both;
        }}
        
        .tool-card {{
            background: rgba(255, 255, 255, 0.2);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 24px;
            padding: 2.5rem;
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            cursor: pointer;
            position: relative;
            overflow: hidden;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            text-decoration: none;
            display: block;
        }}
        
        .tool-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.1) 0%, transparent 100%);
            opacity: 0;
            transition: opacity 0.4s ease;
        }}
        
        .tool-card:hover {{
            transform: translateY(-10px) scale(1.02);
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
            border-color: rgba(255, 255, 255, 0.5);
        }}
        
        .tool-card:hover::before {{ opacity: 1; }}
        
        .tool-icon {{
            font-size: 4rem;
            margin-bottom: 1.5rem;
            display: block;
            filter: drop-shadow(0 4px 8px rgba(0, 0, 0, 0.1));
            transition: transform 0.4s ease;
        }}
        
        .tool-card:hover .tool-icon {{
            transform: scale(1.1) rotate(5deg);
        }}
        
        .tool-title {{
            color: white;
            font-size: 1.75rem;
            font-weight: 700;
            margin-bottom: 1rem;
            text-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }}
        
        .tool-description {{
            color: rgba(255, 255, 255, 0.9);
            font-size: 1rem;
            line-height: 1.6;
            margin-bottom: 1.5rem;
        }}
        
        .tool-footer {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 1.5rem;
        }}
        
        .tool-price {{
            background: rgba(255, 255, 255, 0.3);
            color: white;
            padding: 0.5rem 1rem;
            border-radius: 12px;
            font-weight: 700;
            font-size: 1.1rem;
            border: 1px solid rgba(255, 255, 255, 0.4);
        }}
        
        .new-badge {{
            background: linear-gradient(135deg, #06b6d4 0%, #0891b2 100%);
            color: white;
            padding: 0.4rem 1rem;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            box-shadow: 0 4px 12px rgba(6, 182, 212, 0.4);
            animation: pulse 2s ease-in-out infinite;
        }}
        
        @keyframes pulse {{
            0%, 100% {{ transform: scale(1); }}
            50% {{ transform: scale(1.05); }}
        }}
        
        @media (max-width: 768px) {{
            .tools-grid {{ grid-template-columns: 1fr; }}
            .welcome-title {{ font-size: 2rem; }}
            .navbar {{ flex-direction: column; gap: 1rem; padding: 1rem; }}
            .nav-menu {{ flex-wrap: wrap; justify-content: center; }}
        }}
    </style>
</head>
<body>
    <nav class="navbar">
        <a href="/" class="logo">
            <span class="logo-icon">📅</span>
            <span>AutoDate</span>
        </a>
        <div class="nav-menu">
            <div class="user-badge">
                <span class="user-icon">👤</span>
                {username}
            </div>
            <a href="/" class="nav-link">🏠 Dashboard</a>
            {admin_link}
            <a href="/billing" class="credits-badge">💳 £{credits:.2f}</a>
            <form action="/logout" method="post" style="display: inline;">
                <button type="submit" class="logout-btn">Logout</button>
            </form>
        </div>
    </nav>
    
    <div class="container">
        <div class="welcome-section">
            <h1 class="welcome-title">
                Welcome back, {username.split('@')[0]}! <span class="wave">👋</span>
            </h1>
            <p class="welcome-subtitle">Choose a tool to get started with your project automation</p>
        </div>
        
        <div class="tools-grid">
            {timestamp_card}
            {retrofit_card}
            {ats_card}
            {adf_card}
            {sf70_card}        
        </div>
    </div>
</body>
</html>
    """
    return HTMLResponse(html)

# ============================================================================
# AUTH ROUTES
# ============================================================================

@app.get("/login", response_class=HTMLResponse)
def route_login(request: Request):
    return get_login_page(request)

@app.post("/login")
async def route_post_login(request: Request):
    return await post_login(request)

@app.get("/register", response_class=HTMLResponse)
def route_register():
    return get_register_page()

@app.post("/register")
async def route_post_register(request: Request):
    return await post_register(request)

@app.post("/logout")
def route_logout(request: Request):
    return post_logout(request)

# ============================================================================
# ADMIN ROUTES
# ============================================================================

@app.get("/admin", response_class=HTMLResponse)
async def route_admin_dashboard(request: Request):
    user_row = require_admin(request)
    if isinstance(user_row, RedirectResponse):
        return user_row
    return await get_admin_dashboard(request)

@app.get("/admin/weekly-report", response_class=HTMLResponse)
async def route_admin_weekly_report(request: Request, start_date: str = None):
    user_row = require_admin(request)
    if isinstance(user_row, RedirectResponse):
        return user_row
    return await get_admin_weekly_report(request, start_date)

@app.get("/admin/user/{user_id}", response_class=HTMLResponse)
async def route_admin_user_edit(request: Request, user_id: int):
    user_row = require_admin(request)
    if isinstance(user_row, RedirectResponse):
        return user_row
    return await get_admin_user_edit(request, user_id)

@app.post("/admin/user/{user_id}", response_class=HTMLResponse)
async def route_admin_user_edit_submit(request: Request, user_id: int):
    user_row = require_admin(request)
    if isinstance(user_row, RedirectResponse):
        return user_row
    return await post_admin_user_edit(request, user_id, user_row)
    
# ============================================================================
# BILLING ROUTES
# ============================================================================

@app.get("/billing", response_class=HTMLResponse)
def route_billing(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, RedirectResponse):
        return user_row
    return get_billing_page(request)

@app.get("/billing/topup", response_class=HTMLResponse)
def route_topup(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, RedirectResponse):
        return user_row
    return get_topup_page(request)

@app.post("/billing/topup")
async def route_post_topup(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, RedirectResponse):
        return user_row
    return await post_topup(request, user_row)

# ============================================================================
# TIMESTAMP TOOL ROUTES
# ============================================================================

@app.get("/tool/timestamp", response_class=HTMLResponse)
def route_timestamp_tool(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, RedirectResponse):
        return user_row
    return get_timestamp_tool_page(request)

@app.post("/tool/timestamp/process")
async def route_timestamp_process(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, RedirectResponse):
        return user_row
    return await post_timestamp_tool(request, user_row)

# ============================================================================
# RETROFIT TOOL ROUTES
# ============================================================================

@app.get("/tool/retrofit", response_class=HTMLResponse)
def route_retrofit_tool(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, RedirectResponse):
        return user_row
    return get_retrofit_tool_page(request)

@app.post("/tool/retrofit/process")
async def route_retrofit_process(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, RedirectResponse):
        return user_row
    return await post_retrofit_process(request, user_row)

# ====================================================================================
# ATS GENERATOR TOOL ROUTES
# ====================================================================================

@app.get("/tool/ats-generator", response_class=HTMLResponse)
async def route_ats_generator(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, RedirectResponse):
        return user_row
    return await ats_generator_route(request, user_row)

# ==================================================================================
# ADF CHECKLIST TOOL ROUTES
# ==================================================================================

@app.get("/tool/adf-checklist", response_class=HTMLResponse)
async def route_adf_checklist(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, RedirectResponse):
        return user_row
    return await adf_checklist_route(request, user_row)

@app.post("/tool/adf-checklist")
async def route_adf_checklist_process(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, RedirectResponse):
        return user_row
    return await adf_checklist_route(request, user_row)

@app.post("/tool/ats-generator")
async def route_ats_generator_process(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, RedirectResponse):
        return user_row
    return await ats_generator_route(request, user_row)

# ====================================================================================
# SF70 EEM TOOL ROUTES
# ====================================================================================

@app.get("/tool/sf70", response_class=HTMLResponse)
async def route_sf70_tool(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, RedirectResponse):
        return user_row
    return await sf70_tool_route(request, user_row)

@app.post("/tool/sf70")
async def route_sf70_process(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, RedirectResponse):
        return user_row
    return await sf70_tool_route(request, user_row)

# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
