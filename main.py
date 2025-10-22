"""
RETROFIT DESIGN AUTOMATION TOOL - INITIAL SETUP
Development Branch: retrofit-tool-development
Status: In Development - Not affecting production AutoDate
"""

import io
import json
from typing import Dict, List, Optional
from datetime import datetime
from fastapi import UploadFile, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import require_active_user_row
from database import update_user_credits, add_transaction

# ============================================================================
# CONFIGURATION
# ============================================================================

RETROFIT_TOOL_COST = 5.00  # £5 per design document

# Temporary in-memory storage for development
# TODO: Move to proper database when ready for production
SESSION_STORAGE: Dict[int, dict] = {}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_session_data(user_id: int) -> Optional[dict]:
    """Get session data for a user"""
    return SESSION_STORAGE.get(user_id)

def set_session_data(user_id: int, data: dict):
    """Save session data for a user"""
    SESSION_STORAGE[user_id] = data

def clear_session_data(user_id: int):
    """Clear session data for a user"""
    if user_id in SESSION_STORAGE:
        del SESSION_STORAGE[user_id]

# ============================================================================
# MEASURE DEFINITIONS
# ============================================================================

AVAILABLE_MEASURES = {
    "loft_insulation": {
        "id": "loft_insulation",
        "name": "Loft Insulation",
        "icon": "🏠",
        "description": "Top-up loft insulation to 300mm"
    },
    "cavity_wall": {
        "id": "cavity_wall",
        "name": "Cavity Wall Insulation",
        "icon": "🧱",
        "description": "Cavity wall insulation installation"
    },
    "solar_pv": {
        "id": "solar_pv",
        "name": "Solar PV",
        "icon": "☀️",
        "description": "Solar photovoltaic panels",
        "requires_calc": True
    },
    "heat_pump": {
        "id": "heat_pump",
        "name": "Air Source Heat Pump",
        "icon": "🔥",
        "description": "Air source heat pump installation",
        "requires_calc": True
    },
    "trv": {
        "id": "trv",
        "name": "TRV Installation",
        "icon": "🌡️",
        "description": "Thermostatic radiator valves"
    }
}

# ============================================================================
# ROUTES - LANDING PAGE
# ============================================================================

def get_retrofit_tool_landing(request: Request):
    """Landing page for retrofit design tool"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    try:
        credits = float(user_row.get("credits", 0.0))
    except Exception:
        credits = 0.0
    
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Retrofit Design Tool - AutoDate</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
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
        .credits {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 10px 20px;
            border-radius: 25px;
            font-weight: 600;
            font-size: 18px;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }}
        .hero {{
            text-align: center;
            margin-bottom: 40px;
        }}
        .hero h2 {{
            font-size: 28px;
            color: #333;
            margin-bottom: 15px;
        }}
        .hero p {{
            font-size: 16px;
            color: #666;
            line-height: 1.6;
        }}
        .info-box {{
            background: #e3f2fd;
            border-left: 4px solid #2196f3;
            padding: 20px;
            margin: 30px 0;
            border-radius: 8px;
        }}
        .info-box h3 {{
            color: #1976d2;
            margin-bottom: 10px;
        }}
        .info-box ul {{
            margin-left: 20px;
            color: #555;
            line-height: 1.8;
        }}
        .cost-badge {{
            background: #fff3cd;
            color: #856404;
            padding: 15px 20px;
            border-radius: 8px;
            text-align: center;
            font-weight: 600;
            font-size: 18px;
            margin: 20px 0;
        }}
        .btn {{
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }}
        .btn:hover {{ transform: scale(1.02); }}
        .back-link {{
            display: inline-block;
            margin-top: 20px;
            color: #667eea;
            text-decoration: none;
            font-weight: 600;
        }}
        .dev-notice {{
            background: #fef3c7;
            border: 2px solid #f59e0b;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
        }}
        .dev-notice strong {{
            color: #f59e0b;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🏗️ Retrofit Design Tool</h1>
        <div class="credits">£{credits:.2f}</div>
    </div>
    
    <div class="container">
        <div class="dev-notice">
            <strong>⚠️ DEVELOPMENT VERSION</strong><br>
            This tool is currently in development on the retrofit-tool-development branch
        </div>
        
        <div class="hero">
            <h2>PAS 2035 Compliant Retrofit Design</h2>
            <p>Automated design document generation in under 15 minutes</p>
        </div>
        
        <div class="cost-badge">
            💰 Cost: £{RETROFIT_TOOL_COST:.2f} per design document
        </div>
        
        <div class="info-box">
            <h3>📋 What You'll Need:</h3>
            <ul>
                <li>Site notes (PAS Hub or Elmhurst format)</li>
                <li>Solar calculations (if installing solar PV)</li>
                <li>Heat pump calculations (if installing ASHP)</li>
                <li>10-15 minutes to answer measure-specific questions</li>
            </ul>
        </div>
        
        <div class="info-box">
            <h3>✨ What You'll Get:</h3>
            <ul>
                <li>Complete PAS 2035 compliant design document</li>
                <li>TrustMark audit-proof documentation</li>
                <li>Installation instructions for each measure</li>
                <li>Professional PDF ready for submission</li>
            </ul>
        </div>
        
        <form method="POST" action="/tool/retrofit/start">
            <button type="submit" class="btn">Start New Design Project →</button>
        </form>
        
        <a href="/" class="back-link">← Back to Dashboard</a>
    </div>
</body>
</html>
    """
    return HTMLResponse(html)

# ============================================================================
# ROUTES - START PROJECT
# ============================================================================

async def post_retrofit_start(request: Request):
    """Initialize new project and redirect to upload page"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    user_id = user_row["id"]
    
    # Initialize fresh session data
    session_data = {
        "started_at": datetime.now().isoformat(),
        "site_notes_format": None,
        "site_notes_data": {},
        "selected_measures": [],
        "measure_answers": {},
        "calculations": {}
    }
    
    set_session_data(user_id, session_data)
    
    return RedirectResponse("/tool/retrofit/upload", status_code=303)

# ============================================================================
# ROUTES - UPLOAD DOCUMENTS
# ============================================================================

def get_retrofit_upload(request: Request):
    """Document upload page"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Upload Documents - AutoDate</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #f8fafc;
            color: #0f172a;
        }
        .header {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            color: white;
            padding: 2rem;
            text-align: center;
        }
        .header h1 { font-size: 1.8rem; margin-bottom: 0.5rem; }
        .container {
            max-width: 900px;
            margin: 2rem auto;
            padding: 0 1rem;
        }
        .card {
            background: white;
            border-radius: 12px;
            padding: 2rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 2rem;
        }
        .step-indicator {
            text-align: center;
            margin-bottom: 2rem;
            color: #64748b;
        }
        .upload-box {
            border: 3px dashed #cbd5e1;
            border-radius: 12px;
            padding: 3rem;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
            background: #f8fafc;
        }
        .upload-box:hover {
            border-color: #667eea;
            background: #f0f4ff;
        }
        .upload-icon {
            font-size: 48px;
            margin-bottom: 15px;
        }
        .btn {
            padding: 1rem 2rem;
            border: none;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
        }
        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>📤 Upload Site Notes</h1>
        <p>Step 1 of 4</p>
    </div>
    
    <div class="container">
        <div class="step-indicator">
            <strong>Step 1:</strong> Upload → <span style="color: #cbd5e1;">Step 2: Measures → Step 3: Questions → Step 4: Generate</span>
        </div>
        
        <div class="card">
            <h2 style="margin-bottom: 1.5rem;">Upload Site Notes</h2>
            
            <form method="POST" action="/tool/retrofit/upload" enctype="multipart/form-data">
                <div class="upload-box" onclick="document.getElementById('siteNotesFile').click()">
                    <div class="upload-icon">📄</div>
                    <h3>Click or drag site notes here</h3>
                    <p style="color: #64748b; margin-top: 10px;">
                        Supports PAS Hub and Elmhurst formats (PDF)
                    </p>
                </div>
                <input type="file" id="siteNotesFile" name="site_notes" accept=".pdf" style="display: none;">
                
                <div style="margin-top: 2rem; text-align: center;">
                    <button type="submit" class="btn btn-primary">
                        Continue to Measure Selection →
                    </button>
                </div>
            </form>
        </div>
    </div>
</body>
</html>
    """
    return HTMLResponse(html)

# ============================================================================
# PLACEHOLDER ROUTES (To be built)
# ============================================================================

def get_retrofit_measures(request: Request):
    """Measure selection page - TO BE BUILT"""
    return HTMLResponse("<h1>Measure Selection - Coming Soon</h1>")

def get_retrofit_questions(request: Request):
    """Questions page - TO BE BUILT"""
    return HTMLResponse("<h1>Questions - Coming Soon</h1>")

def get_retrofit_generate(request: Request):
    """Generate document page - TO BE BUILT"""
    return HTMLResponse("<h1>Generate Document - Coming Soon</h1>")
