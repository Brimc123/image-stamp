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
from admin import get_admin_dashboard, get_admin_weekly_report, get_admin_user_edit, post_admin_user_edit, post_admin_user_delete

from billing import get_billing_page, get_topup_page, post_topup
from timestamp_tool import get_timestamp_tool_page, post_timestamp_tool
from retrofit_tool import get_retrofit_tool_page, post_retrofit_process
from ats_tool import ats_generator_route
from adf_tool import adf_checklist_route
from sf70_tool import sf70_tool_route
from pas2035_docs_tool import generate_pas2035_documents, save_document_to_bytes

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
    pas2035_access = user_row.get("pas2035_tool_access", 1) == 1

    # Build tool cards HTML based on access
    timestamp_card = f'''<a href="/tool/timestamp" class="tool-card">
                <span class="tool-icon"⏱️</span>
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

    pas2035_card = f'''<a href="/tool/pas2035-docs" class="tool-card">
                <span class="tool-icon">📋</span>
                <h2 class="tool-title">PAS 2035 Documents Generator</h2>
                <p class="tool-description">
                    Generate SF48 Claim of Compliance Certificate, Customer Introduction Letter, and Handover Letter. All documents are PAS 2035 compliant and professionally formatted.
                </p>
                <div class="tool-footer">
                    <span class="tool-price">💰 £15.00 per use</span>
                    <span class="new-badge">✨ New</span>
                </div>
            </a>''' if pas2035_access else ''
    
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
            {pas2035_card}        
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


@app.post("/admin/user/{user_id}/delete", response_class=HTMLResponse)
async def route_admin_user_delete(request: Request, user_id: int):
    user_row = require_admin(request)
    if isinstance(user_row, RedirectResponse):
        return user_row
    return await post_admin_user_delete(request, user_id)
    
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

# ==================================================================================
# PAS 2035 DOCUMENTS GENERATOR ROUTES
# ==================================================================================

@app.get("/tool/pas2035-docs", response_class=HTMLResponse)
async def route_pas2035_form(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, RedirectResponse):
        return user_row
    
    username = user_row.get("username", "User")
    credits = user_row.get("credits", 0.0)

    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>PAS 2035 Documents Generator - AutoDate</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }}
            .navbar {{
                background: white;
                padding: 1rem 2rem;
                border-radius: 10px;
                margin-bottom: 2rem;
                display: flex;
                justify-content: space-between;
                align-items: center;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            .nav-left a {{
                color: #667eea;
                text-decoration: none;
                font-weight: 500;
            }}
            .user-info {{ color: #666; }}
            .credits {{ color: #10b981; font-weight: bold; }}
            .container {{
                max-width: 900px;
                margin: 0 auto;
                background: white;
                padding: 40px;
                border-radius: 15px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #667eea;
                margin-bottom: 10px;
                font-size: 2rem;
            }}
            .subtitle {{
                color: #666;
                margin-bottom: 30px;
                font-size: 1.1rem;
            }}
            .price-tag {{
                background: #10b981;
                color: white;
                padding: 8px 16px;
                border-radius: 20px;
                font-weight: 600;
                display: inline-block;
                margin-bottom: 20px;
            }}
            .info-box {{
                background: #e0e7ff;
                border-left: 4px solid #667eea;
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 20px;
            }}
            .info-box h3 {{
                color: #667eea;
                margin-bottom: 10px;
            }}
            .info-box ul {{
                margin-left: 20px;
                color: #555;
            }}
            .form-group {{
                margin-bottom: 20px;
            }}
            label {{
                display: block;
                margin-bottom: 8px;
                color: #333;
                font-weight: 500;
            }}
            input[type="text"], textarea, input[type="date"] {{
                width: 100%;
                padding: 12px;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                font-size: 14px;
                transition: border-color 0.3s;
            }}
            input:focus, textarea:focus {{
                outline: none;
                border-color: #667eea;
            }}
            textarea {{
                resize: vertical;
                min-height: 80px;
            }}
            .measures-grid {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 15px;
                margin-top: 10px;
            }}
            .checkbox-item {{
                display: flex;
                align-items: center;
                padding: 12px;
                background: #f8f9fa;
                border-radius: 8px;
                cursor: pointer;
                transition: background 0.3s;
            }}
            .checkbox-item:hover {{
                background: #e9ecef;
            }}
            .checkbox-item input[type="checkbox"] {{
                width: 20px;
                height: 20px;
                margin-right: 10px;
                cursor: pointer;
            }}
            .radio-group {{
                display: flex;
                gap: 20px;
                margin-top: 10px;
            }}
            .radio-item {{
                display: flex;
                align-items: center;
            }}
            .radio-item input[type="radio"] {{
                width: 18px;
                height: 18px;
                margin-right: 8px;
                cursor: pointer;
            }}
            .submit-btn {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 15px 40px;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.2s;
                width: 100%;
                margin-top: 20px;
            }}
            .submit-btn:hover {{
                transform: translateY(-2px);
            }}
        </style>
    </head>
    <body>
        <div class="navbar">
            <div class="nav-left">
                <a href="/">← Back to Dashboard</a>
            </div>
            <div class="user-info">
                {username} | <span class="credits">£{credits:.2f}</span>
            </div>
        </div>

        <div class="container">
            <h1>📋 PAS 2035 Documents Generator</h1>
            <p class="subtitle">Generate SF48 Certificate, Introduction Letter & Handover Letter</p>
            <div class="price-tag">💰 £15.00 per use</div>

            <div class="info-box">
                <h3>📄 This tool generates 3 professional documents:</h3>
                <ul>
                    <li>SF48 Claim of Compliance Certificate (PAS 2035)</li>
                    <li>Customer Introduction Letter</li>
                    <li>Customer Handover Letter with Conflict of Interest Declaration</li>
                </ul>
            </div>

            <form action="/tool/pas2035-docs/generate" method="post">
                <div class="form-group">
                    <label>Retrofit Coordinator ID *</label>
                    <input type="text" name="rc_id" required placeholder="e.g., RC-2024-001">
                </div>

                <div class="form-group">
                    <label>Retrofit Coordinator Name *</label>
                    <input type="text" name="rc_name" required placeholder="Full name">
                </div>

                <div class="form-group">
                    <label>Property Address *</label>
                    <textarea name="property_address" required placeholder="Full property address"></textarea>
                </div>

                <div class="form-group">
                    <label>Customer Name *</label>
                    <input type="text" name="customer_name" required placeholder="Full customer name">
                </div>

                <div class="form-group">
                    <label>Customer Address *</label>
                    <textarea name="customer_address" required placeholder="Customer correspondence address"></textarea>
                </div>

                <div class="form-group">
                    <label>Installer Name *</label>
                    <input type="text" name="installer_name" required placeholder="Installation company name">
                </div>

                <div class="form-group">
                    <label>Installer Contact *</label>
                    <input type="text" name="installer_contact" required placeholder="Phone/Email">
                </div>

                <div class="form-group">
                    <label>Installation Start Date *</label>
                    <input type="date" name="install_start_date" required>
                </div>

                <div class="form-group">
                    <label>Project Completion Date *</label>
                    <input type="date" name="project_date" required>
                </div>

                <div class="form-group">
                    <label>Select Retrofit Measures Installed *</label>
                    <div class="measures-grid">
                        <label class="checkbox-item">
                            <input type="checkbox" name="measures" value="RIR">
                            Roof Insulation & Repair
                        </label>
                        <label class="checkbox-item">
                            <input type="checkbox" name="measures" value="IWI">
                            Internal Wall Insulation
                        </label>
                        <label class="checkbox-item">
                            <input type="checkbox" name="measures" value="LOFT">
                            Loft Insulation
                        </label>
                        <label class="checkbox-item">
                            <input type="checkbox" name="measures" value="GAS_BOILER">
                            Gas Boiler
                        </label>
                        <label class="checkbox-item">
                            <input type="checkbox" name="measures" value="ESH">
                            Electric Storage Heaters
                        </label>
                        <label class="checkbox-item">
                            <input type="checkbox" name="measures" value="ASHP">
                            Air Source Heat Pump
                        </label>
                        <label class="checkbox-item">
                            <input type="checkbox" name="measures" value="SOLAR">
                            Solar PV Panels
                        </label>
                        <label class="checkbox-item">
                            <input type="checkbox" name="measures" value="CWI">
                            Cavity Wall Insulation
                        </label>
                        <label class="checkbox-item">
                            <input type="checkbox" name="measures" value="UFI">
                            Underfloor Insulation
                        </label>
                        <label class="checkbox-item">
                            <input type="checkbox" name="measures" value="HEATING_CONTROLS">
                            Heating Controls
                        </label>
                    </div>
                </div>

                <div class="form-group">
                    <label>Conflict of Interest? *</label>
                    <div class="radio-group">
                        <label class="radio-item">
                            <input type="radio" name="conflict_of_interest" value="No" checked>
                            No
                        </label>
                        <label class="radio-item">
                            <input type="radio" name="conflict_of_interest" value="Yes">
                            Yes
                        </label>
                    </div>
                </div>

                <button type="submit" class="submit-btn">Generate Documents (£15.00)</button>
            </form>
        </div>
    </body>
    </html>
    """)

  
@app.post("/tool/pas2035-docs/generate")
async def route_pas2035_generate(request: Request):
    """Generate PAS 2035 documents"""
    import io
    import zipfile
    from datetime import datetime
    
    user_row = require_active_user_row(request)
    if isinstance(user_row, RedirectResponse):
        return user_row
    
    user_id = user_row.get("id")
    current_credits = user_row.get("credits", 0.0)
    tool_cost = 15.0
    is_admin = user_row.get("is_admin", 0) == 1
    
    # Check credits
    if not is_admin and current_credits < tool_cost:
        return HTMLResponse(f"""
            <script>
                alert("Insufficient credits! You need £{tool_cost:.2f} but have £{current_credits:.2f}");
                window.location.href = "/billing/topup";
            </script>
        """)
    
    # Get form data
    form = await request.form()
    measures_list = form.getlist('measures')
    
    form_data = {
        'rc_id': form.get('rc_id'),
        'rc_name': form.get('rc_name'),
        'property_address': form.get('property_address'),
        'customer_name': form.get('customer_name'),
        'customer_address': form.get('customer_address'),
        'installer_name': form.get('installer_name'),
        'installer_contact': form.get('installer_contact'),
        'install_start_date': form.get('install_start_date'),
        'project_date': form.get('project_date'),
        'conflict_of_interest': form.get('conflict_of_interest', 'No'),
        'measures': measures_list
    }
    
    # Generate documents
    sf48_doc, intro_doc, handover_doc = generate_pas2035_documents(form_data)
    
    # Save to bytes
    sf48_bytes = save_document_to_bytes(sf48_doc)
    intro_bytes = save_document_to_bytes(intro_doc)
    handover_bytes = save_document_to_bytes(handover_doc)
    
    # Deduct credits (unless admin)
    if not is_admin:
        new_credits = current_credits - tool_cost
        update_user_credits(user_id, new_credits)
        add_transaction(user_id, -tool_cost, "tool_use", f"PAS 2035 Documents - {form_data['property_address']}")
        log_usage(user_id, "PAS 2035 Documents", tool_cost, f"Generated 3 documents for {form_data['property_address']}")
    else:
        log_usage(user_id, "PAS 2035 Documents", 0.0, f"Admin use - {form_data['property_address']}")
    
    # Create ZIP file with all 3 documents
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr('SF48_Claim_of_Compliance.docx', sf48_bytes.getvalue())
        zip_file.writestr('Customer_Introduction_Letter.docx', intro_bytes.getvalue())
        zip_file.writestr('Customer_Handover_Letter.docx', handover_bytes.getvalue())
    
    zip_buffer.seek(0)
    
    # Return ZIP file
    filename = f"PAS2035_Documents_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    ) 

# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
