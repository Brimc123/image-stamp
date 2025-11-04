"""
RETROFIT DESIGN TOOL - UPDATED WITH GENERIC INSTALLATION INSTRUCTIONS
✅ Updated filename mappings to use generic instruction files
"""

import io
import os
import re
import json
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
import PyPDF2
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import openpyxl

from auth import require_active_user_row
from database import update_user_credits, add_transaction
from config import RETROFIT_TOOL_COST

# Session storage (in-memory for now)
SESSION_STORAGE = {}

# ============================================================================
# INSTALLATION INSTRUCTIONS FUNCTIONS
# ============================================================================

def load_installation_instructions(measure_code: str) -> str:
    """Load installation instructions from text file"""
    # ✅ UPDATED: Map measure codes to GENERIC filenames
    filename_mapping = {
        "HEAT_PUMP": "Heat_Pump.txt",
        "CWI": "Cavity_Wall_Insulation.txt",
        "ESH": "Electric_Storage_Heaters.txt",
        "IWI": "Internal_Wall_Insulation.txt",
        "LOFT": "Loft_Insulation.txt",
        "PRT": "Heating_Controls.txt",  # ✅ Generic controls file (create later)
        "RIR": "Room_in_Roof_Insulation.txt",
        "SOLAR_PV": "Solar_PV.txt",
        "TRV": "Heating_Controls.txt",  # ✅ Generic controls file (create later)
        "GAS_BOILER": "Gas_Boiler.txt"
    }
    
    filename = filename_mapping.get(measure_code, f"{measure_code}.txt")
    filepath = os.path.join("installation_instructions", filename)
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return f"Installation instructions for {measure_code} not available at {filepath}."
    except Exception as e:
        return f"Error loading installation instructions for {measure_code}: {str(e)}"

def format_installation_instructions_for_pdf(instructions: str) -> str:
    """Format installation instructions for PDF inclusion"""
    # Add some basic formatting for PDF
    formatted = instructions.replace('\n\n', '<br/><br/>')
    formatted = formatted.replace('\n', '<br/>')
    
    # Make numbered sections bold
    formatted = re.sub(r'^(\d+\.\s+[A-Z][A-Z\s]+)$', r'<b>\1</b>', formatted, flags=re.MULTILINE)
    
    return formatted

# ============================================================================
# MEASURE DEFINITIONS
# ============================================================================

MEASURES = {
    "LOFT": {
        "name": "Loft Insulation",
        "code": "LOFT",
        "icon": "🏠",
        "requires_calc": False,
        "questions": [
            {"id": "area", "label": "Area being treated (m²)", "type": "number"},
            {"id": "current_depth", "label": "Existing loft insulation thickness (mm)", "type": "number"},
            {"id": "new_depth", "label": "New insulation depth (mm)", "type": "number", "default": 300}
        ]
    },
    "ESH": {
        "name": "Electric Storage Heaters",
        "code": "ESH",
        "icon": "🔌",
        "requires_calc": True,
        "questions": [
            {"id": "manufacturer", "label": "Manufacturer", "type": "text"},
            {"id": "model", "label": "Model numbers", "type": "text"},
            {"id": "heater_count", "label": "Number of heaters", "type": "number"},
            {"id": "total_capacity", "label": "Total capacity (kW)", "type": "number"},
            {"id": "heat_calc", "label": "Heat Demand Calculator included?", "type": "select", "options": ["Yes", "No"]}
        ]
    },
    "PRT": {
        "name": "Programmable Room Thermostat",
        "code": "PRT",
        "icon": "🌡️",
        "requires_calc": False,
        "questions": [
            {"id": "make_model", "label": "Make and model being installed", "type": "text"}
        ]
    },
    "TRV": {
        "name": "Thermostatic Radiator Valves",
        "code": "TRV",
        "icon": "🌡️",
        "requires_calc": False,
        "questions": [
            {"id": "make_model", "label": "Make and model being installed", "type": "text"},
            {"id": "quantity", "label": "Number of TRVs being installed", "type": "number"}
        ]
    },
    "GAS_BOILER": {
        "name": "Gas Boiler",
        "code": "GAS_BOILER",
        "icon": "🔥",
        "requires_calc": False,
        "questions": [
            {"id": "make_model", "label": "Make and model being installed", "type": "text"},
            {"id": "size", "label": "Boiler KW size required", "type": "number"},
            {"id": "heat_calc", "label": "Heat Demand Calculator included?", "type": "select", "options": ["Yes", "No"]}
        ]
    },
    "HEAT_PUMP": {
        "name": "Air Source Heat Pump",
        "code": "HEAT_PUMP",
        "icon": "♨️",
        "requires_calc": True,
        "questions": [
            {"id": "make_model", "label": "Make and model being installed", "type": "text"},
            {"id": "capacity", "label": "Heat pump size required (kW)", "type": "number"},
            {"id": "scop", "label": "SCOP rating", "type": "number"},
            {"id": "heat_calc", "label": "Heat Demand Calculator included?", "type": "select", "options": ["Yes", "No"]}
        ]
    },
    "SOLAR_PV": {
        "name": "Solar PV",
        "code": "SOLAR_PV",
        "icon": "☀️",
        "requires_calc": True,
        "questions": [
            {"id": "make_model", "label": "Make and model being installed", "type": "text"},
            {"id": "system_size", "label": "System size (kW)", "type": "number"},
            {"id": "calcs_included", "label": "Solar PV Calculations included?", "type": "select", "options": ["Yes", "No"]}
        ]
    },
    "IWI": {
        "name": "Internal Wall Insulation",
        "code": "IWI",
        "icon": "🧱",
        "requires_calc": False,
        "questions": [
            {"id": "area", "label": "Area being treated (m²)", "type": "number"},
            {"id": "rooms_omitted", "label": "Rooms being omitted from install?", "type": "text"}
        ]
    },
    "CWI": {
        "name": "Cavity Wall Insulation",
        "code": "CWI",
        "icon": "🧱",
        "requires_calc": False,
        "questions": [
            {"id": "area", "label": "Area being treated (m²)", "type": "number"}
        ]
    },
    "RIR": {
        "name": "Room in Roof",
        "code": "RIR",
        "icon": "🏠",
        "requires_calc": False,
        "questions": [
            {"id": "area", "label": "Area being treated (m²)", "type": "number"}
        ]
    }
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_session_data(user_id: int) -> Optional[Dict]:
    return SESSION_STORAGE.get(user_id)

def store_session_data(user_id: int, data: Dict):
    SESSION_STORAGE[user_id] = data

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        print(f"PDF extraction error: {e}")
        return ""

def extract_property_data(text: str) -> Dict:
    """Extract property data from site notes - IMPROVED LOFT EXTRACTION"""
    data = {}
    
    # Address patterns
    address_match = re.search(r'(?:Property Address|Address)[:\s]+(.*?)(?:\n|$)', text, re.IGNORECASE)
    if address_match:
        data['address'] = address_match.group(1).strip()
    
    # Loft patterns - IMPROVED
    loft_patterns = [
        r'loft.*?insulation.*?(\d+)\s*mm',
        r'roof.*?insulation.*?(\d+)\s*mm',
        r'insulation.*?thickness.*?(\d+)\s*mm',
        r'loft.*?(\d+)\s*mm.*?insulation'
    ]
    
    for pattern in loft_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            data['loft_current_depth'] = match.group(1)
            break
    
    return data

# ============================================================================
# ROUTES
# ============================================================================

def get_retrofit_start(request: Request):
    """Initial page - upload documents"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    user_id = user_row["id"]
    
    # Clear any existing session
    if user_id in SESSION_STORAGE:
        del SESSION_STORAGE[user_id]
    
    html = """
<!DOCTYPE html>
<html>
<head>
    <title>Retrofit Design Tool - AutoDate</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 {
            color: #667eea;
            margin-bottom: 10px;
            font-size: 32px;
        }
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 16px;
        }
        .section-title {
            font-size: 20px;
            font-weight: 600;
            color: #333;
            margin: 30px 0 15px 0;
        }
        .format-selector {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin-bottom: 30px;
        }
        .format-card {
            border: 2px solid #e0e0e0;
            border-radius: 12px;
            padding: 20px;
            cursor: pointer;
            transition: all 0.3s;
            text-align: center;
        }
        .format-card:hover {
            border-color: #667eea;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.2);
        }
        .format-card.selected {
            border-color: #667eea;
            background: #f0f4ff;
        }
        .format-icon {
            font-size: 48px;
            margin-bottom: 10px;
        }
        .format-name {
            font-weight: 600;
            color: #333;
        }
        .input-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
            color: #333;
        }
        input[type="text"] {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
        }
        .upload-box {
            border: 2px dashed #ccc;
            border-radius: 12px;
            padding: 30px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
            margin-bottom: 15px;
        }
        .upload-box:hover {
            border-color: #667eea;
            background: #f9f9ff;
        }
        .upload-box.has-file {
            border-color: #4caf50;
            background: #f1f8f4;
        }
        .upload-icon {
            font-size: 48px;
            margin-bottom: 10px;
        }
        .upload-text {
            font-size: 18px;
            font-weight: 600;
            color: #333;
            margin-bottom: 5px;
        }
        .upload-subtext {
            color: #666;
            font-size: 14px;
        }
        .file-name {
            color: #4caf50;
            font-weight: 600;
            margin-top: 10px;
        }
        input[type="file"] {
            display: none;
        }
        .btn {
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            margin-top: 30px;
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🏠 Retrofit Design Tool</h1>
        <p class="subtitle">Create PAS 2035 compliant retrofit design documents</p>
        
        <form method="POST" action="/tool/retrofit/upload" enctype="multipart/form-data">
            <!-- Format Selection -->
            <div class="section-title">📋 Step 1: Select Site Notes Format</div>
            <div class="format-selector">
                <div class="format-card" onclick="selectFormat('PAS Hub', this)">
                    <input type="radio" name="format_style" value="PAS Hub" id="format_pashub" required style="display:none;">
                    <div class="format-icon">📘</div>
                    <div class="format-name">PAS Hub</div>
                </div>
                <div class="format-card" onclick="selectFormat('Elmhurst', this)">
                    <input type="radio" name="format_style" value="Elmhurst" id="format_elmhurst" required style="display:none;">
                    <div class="format-icon">📗</div>
                    <div class="format-name">Elmhurst</div>
                </div>
            </div>
            
            <!-- Project Info -->
            <div class="section-title">📝 Step 2: Project Information</div>
            <div class="input-group">
                <label for="project_name">Project Name:</label>
                <input type="text" id="project_name" name="project_name" required>
            </div>
            <div class="input-group">
                <label for="coordinator">Retrofit Coordinator Name:</label>
                <input type="text" id="coordinator" name="coordinator" required>
            </div>
            
            <!-- Document Uploads -->
            <div class="section-title">📤 Step 3: Upload Documents</div>
            
            <div class="upload-box" id="siteNotesBox" onclick="document.getElementById('siteNotes').click()">
                <div class="upload-icon">📄</div>
                <div class="upload-text">Site Notes (Required)</div>
                <div class="upload-subtext">Drag & drop or click to browse</div>
                <div class="file-name" id="siteNotesName"></div>
            </div>
            <input type="file" id="siteNotes" name="site_notes" accept=".pdf" required>
            
            <div class="upload-box" id="conditionBox" onclick="document.getElementById('conditionReport').click()">
                <div class="upload-icon">📋</div>
                <div class="upload-text">Condition Report (Required)</div>
                <div class="upload-subtext">Drag & drop or click to browse</div>
                <div class="file-name" id="conditionName"></div>
            </div>
            <input type="file" id="conditionReport" name="condition_report" accept=".pdf" required>
            
            <div class="upload-box" id="measureBox" onclick="document.getElementById('measureSheet').click()">
                <div class="upload-icon">📊</div>
                <div class="upload-text">Measure Sheet (Optional)</div>
                <div class="upload-subtext">Excel file for fallback data</div>
                <div class="file-name" id="measureName"></div>
            </div>
            <input type="file" id="measureSheet" name="measure_sheet" accept=".xlsx,.xls">
            
            <button type="submit" class="btn">Continue to Measure Selection →</button>
        </form>
    </div>
    
    <script>
        function selectFormat(format, element) {
            document.querySelectorAll('.format-card').forEach(card => card.classList.remove('selected'));
            element.classList.add('selected');
            document.getElementById('format_' + format.toLowerCase().replace(' ', '')).checked = true;
        }
        
        function setupDragDrop(boxId, inputId, nameId) {
            const box = document.getElementById(boxId);
            const input = document.getElementById(inputId);
            const nameDiv = document.getElementById(nameId);
            
            ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
                box.addEventListener(eventName, preventDefaults, false);
            });
            
            function preventDefaults(e) {
                e.preventDefault();
                e.stopPropagation();
            }
            
            ['dragenter', 'dragover'].forEach(eventName => {
                box.addEventListener(eventName, () => box.classList.add('dragover'), false);
            });
            
            ['dragleave', 'drop'].forEach(eventName => {
                box.addEventListener(eventName, () => box.classList.remove('dragover'), false);
            });
            
            box.addEventListener('drop', function(e) {
                const dt = e.dataTransfer;
                const files = dt.files;
                input.files = files;
                handleFiles(files, boxId, nameId);
            });
            
            input.addEventListener('change', function(e) {
                handleFiles(e.target.files, boxId, nameId);
            });
            
            function handleFiles(files, boxId, nameId) {
                if (files.length > 0) {
                    const fileName = files[0].name;
                    document.getElementById(nameId).textContent = '✓ ' + fileName;
                    document.getElementById(boxId).classList.add('has-file');
                }
            }
        }
        
        setupDragDrop('siteNotesBox', 'siteNotes', 'siteNotesName');
        setupDragDrop('conditionBox', 'conditionReport', 'conditionName');
        setupDragDrop('measureBox', 'measureSheet', 'measureName');
    </script>
</body>
</html>
    """
    return HTMLResponse(html)

async def post_upload(request: Request):
    """Handle file uploads and extract data"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    user_id = user_row["id"]
    
    try:
        form = await request.form()
        
        # Store basic info
        session_data = {
            "format_style": form.get("format_style"),
            "project_name": form.get("project_name"),
            "coordinator": form.get("coordinator"),
            "extracted_data": {}
        }
        
        # Extract from site notes
        site_notes = form.get("site_notes")
        if site_notes:
            site_notes_bytes = await site_notes.read()
            site_notes_text = extract_text_from_pdf(site_notes_bytes)
            extracted = extract_property_data(site_notes_text)
            session_data["extracted_data"].update(extracted)
        
        store_session_data(user_id, session_data)
        
        return RedirectResponse("/tool/retrofit/measures", status_code=303)
        
    except Exception as e:
        print(f"Upload error: {e}")
        return RedirectResponse("/tool/retrofit", status_code=303)

def get_measures(request: Request):
    """Measure selection page"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    measure_cards = ""
    for code, measure in MEASURES.items():
        measure_cards += f"""
        <div class="measure-card" onclick="toggleMeasure('{code}', this)">
            <input type="checkbox" name="measures" value="{code}" id="measure_{code}" style="display:none;">
            <div class="measure-icon">{measure['icon']}</div>
            <div class="measure-name">{measure['name']}</div>
        </div>
        """
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Select Measures - Retrofit Tool</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }}
        h1 {{
            color: #667eea;
            margin-bottom: 30px;
        }}
        .measures-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .measure-card {{
            border: 2px solid #e0e0e0;
            border-radius: 12px;
            padding: 30px;
            cursor: pointer;
            transition: all 0.3s;
            text-align: center;
        }}
        .measure-card:hover {{
            border-color: #667eea;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.2);
        }}
        .measure-card.selected {{
            border-color: #667eea;
            background: #f0f4ff;
        }}
        .measure-icon {{
            font-size: 48px;
            margin-bottom: 10px;
        }}
        .measure-name {{
            font-weight: 600;
            color: #333;
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
        }}
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔧 Select Retrofit Measures</h1>
        
        <form method="POST" action="/tool/retrofit/measures">
            <div class="measures-grid">
                {measure_cards}
            </div>
            
            <button type="submit" class="btn">Continue to Questions →</button>
        </form>
    </div>
    
    <script>
        function toggleMeasure(code, element) {{
            element.classList.toggle('selected');
            const checkbox = document.getElementById('measure_' + code);
            checkbox.checked = !checkbox.checked;
        }}
    </script>
</body>
</html>
    """
    return HTMLResponse(html)

async def post_measures(request: Request):
    """Store selected measures"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    user_id = user_row["id"]
    session_data = get_session_data(user_id)
    
    if not session_data:
        return RedirectResponse("/tool/retrofit", status_code=303)
    
    try:
        form = await request.form()
        selected_measures = form.getlist("measures")
        
        if not selected_measures:
            return RedirectResponse("/tool/retrofit/measures", status_code=303)
        
        session_data["selected_measures"] = selected_measures
        session_data["current_measure_index"] = 0
        
        store_session_data(user_id, session_data)
        
        # Check if any measures need calculations
        measures_needing_calcs = [m for m in selected_measures if MEASURES[m]["requires_calc"]]
        
        if measures_needing_calcs:
            return RedirectResponse("/tool/retrofit/calcs", status_code=303)
        else:
            return RedirectResponse("/tool/retrofit/questions", status_code=303)
            
    except Exception as e:
        print(f"Error in post_measures: {e}")
        return RedirectResponse("/tool/retrofit/measures", status_code=303)

def get_questions(request: Request):
    """Display questions for current measure"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    user_id = user_row["id"]
    session_data = get_session_data(user_id)
    
    if not session_data or "selected_measures" not in session_data:
        return RedirectResponse("/tool/retrofit", status_code=303)
    
    selected_measures = session_data["selected_measures"]
    current_index = session_data.get("current_measure_index", 0)
    
    # Check if all measures complete
    if current_index >= len(selected_measures):
        return RedirectResponse("/tool/retrofit/generate", status_code=303)
    
    current_measure_code = selected_measures[current_index]
    current_measure = MEASURES[current_measure_code]
    
    # Build question form
    question_fields = ""
    for q in current_measure["questions"]:
        if q["type"] == "number":
            question_fields += f"""
            <div class="input-group">
                <label for="{q['id']}">{q['label']}</label>
                <input type="number" id="{q['id']}" name="{q['id']}" step="any" required>
            </div>
            """
        elif q["type"] == "text":
            question_fields += f"""
            <div class="input-group">
                <label for="{q['id']}">{q['label']}</label>
                <input type="text" id="{q['id']}" name="{q['id']}" required>
            </div>
            """
        elif q["type"] == "select":
            options = "".join([f'<option value="{opt}">{opt}</option>' for opt in q["options"]])
            question_fields += f"""
            <div class="input-group">
                <label for="{q['id']}">{q['label']}</label>
                <select id="{q['id']}" name="{q['id']}" required>
                    {options}
                </select>
            </div>
            """
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Questions - {current_measure['name']}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }}
        h1 {{
            color: #667eea;
            margin-bottom: 30px;
        }}
        .progress {{
            background: #e0e0e0;
            height: 8px;
            border-radius: 4px;
            margin-bottom: 30px;
        }}
        .progress-bar {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            height: 100%;
            border-radius: 4px;
            width: {((current_index + 1) / len(selected_measures)) * 100}%;
            transition: width 0.3s;
        }}
        .input-group {{
            margin-bottom: 20px;
        }}
        label {{
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
            color: #333;
        }}
        input, select {{
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
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
            margin-top: 30px;
        }}
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{current_measure['icon']} {current_measure['name']}</h1>
        <div class="progress">
            <div class="progress-bar"></div>
        </div>
        <p style="margin-bottom: 20px; color: #666;">Question {current_index + 1} of {len(selected_measures)}</p>
        
        <form method="POST" action="/tool/retrofit/questions">
            <input type="hidden" name="measure_code" value="{current_measure_code}">
            {question_fields}
            <button type="submit" class="btn">Continue →</button>
        </form>
    </div>
</body>
</html>
    """
    return HTMLResponse(html)

async def post_questions_submit(request: Request):
    """Handle question submission"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    user_id = user_row["id"]
    session_data = get_session_data(user_id)
    
    if not session_data:
        return RedirectResponse("/tool/retrofit", status_code=303)
    
    try:
        form = await request.form()
        measure_code = form.get("measure_code")
        
        # Store answers
        if 'answers' not in session_data:
            session_data['answers'] = {}
        
        session_data['answers'][measure_code] = dict(form)
        session_data['current_measure_index'] += 1
        
        store_session_data(user_id, session_data)
        
        return RedirectResponse("/tool/retrofit/questions", status_code=303)
        
    except Exception as e:
        print(f"Error in post_questions_submit: {e}")
        return RedirectResponse("/tool/retrofit/questions", status_code=303)

# ============================================================================
# PHASE 4 & 5: GENERATE PDF WITH INSTALLATION INSTRUCTIONS
# ============================================================================

def get_pdf_download(request: Request):
    """Generate and download PDF with installation instructions"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    user_id = user_row["id"]
    session_data = get_session_data(user_id)
    
    if not session_data:
        return RedirectResponse("/tool/retrofit", status_code=303)
    
    # Generate PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#667eea'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    story.append(Paragraph("Retrofit Design & Installation Plan", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Project info
    story.append(Paragraph(f"<b>Project:</b> {session_data.get('project_name', 'N/A')}", styles['Normal']))
    story.append(Paragraph(f"<b>Coordinator:</b> {session_data.get('coordinator', 'N/A')}", styles['Normal']))
    story.append(Paragraph(f"<b>Format:</b> {session_data.get('format_style', 'N/A')}", styles['Normal']))
    story.append(Paragraph(f"<b>Date:</b> {datetime.now().strftime('%d/%m/%Y')}", styles['Normal']))
    story.append(Spacer(1, 0.5*inch))
    
    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 1: DESIGN SPECIFICATIONS
    # ═══════════════════════════════════════════════════════════════════════
    
    section_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontSize=18,
        textColor=colors.HexColor('#667eea'),
        spaceAfter=20,
        spaceBefore=20
    )
    
    story.append(Paragraph("═" * 80, styles['Normal']))
    story.append(Paragraph("SECTION 1: DESIGN SPECIFICATIONS", section_style))
    story.append(Paragraph("═" * 80, styles['Normal']))
    story.append(Spacer(1, 0.3*inch))
    
    # Each measure with specifications
    for measure_code in session_data.get("selected_measures", []):
        measure = MEASURES[measure_code]
        answers = session_data.get("answers", {}).get(measure_code, {})
        
        # Measure heading
        story.append(Paragraph(f"<b>{measure['name']}</b>", styles['Heading3']))
        story.append(Spacer(1, 0.1*inch))
        
        # Measure specifications
        for key, value in answers.items():
            if key != "measure_code":
                story.append(Paragraph(f"• <b>{key}:</b> {value}", styles['Normal']))
        
        story.append(Spacer(1, 0.3*inch))
    
    story.append(PageBreak())
    
    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 2: INSTALLATION INSTRUCTIONS
    # ═══════════════════════════════════════════════════════════════════════
    
    story.append(Paragraph("═" * 80, styles['Normal']))
    story.append(Paragraph("SECTION 2: INSTALLATION INSTRUCTIONS", section_style))
    story.append(Paragraph("═" * 80, styles['Normal']))
    story.append(Spacer(1, 0.3*inch))
    
    # Each measure with installation instructions
    for measure_code in session_data.get("selected_measures", []):
        measure = MEASURES[measure_code]
        
        # Measure heading
        story.append(Paragraph(f"<b>{measure['name'].upper()} - INSTALLATION PROCEDURE</b>", styles['Heading3']))
        story.append(Spacer(1, 0.2*inch))
        
        # Load and format installation instructions
        instructions = load_installation_instructions(measure_code)
        formatted_instructions = format_installation_instructions_for_pdf(instructions)
        
        # Split instructions into paragraphs for better PDF formatting
        instruction_paragraphs = formatted_instructions.split('<br/><br/>')
        for para in instruction_paragraphs:
            if para.strip():
                story.append(Paragraph(para.strip(), styles['Normal']))
                story.append(Spacer(1, 0.1*inch))
        
        story.append(PageBreak())
    
    # Build PDF
    doc.build(story)
    
    # Deduct credits
    try:
        new_credits = float(user_row.get("credits", 0.0)) - RETROFIT_TOOL_COST
        update_user_credits(user_id, new_credits)
        add_transaction(user_id, -RETROFIT_TOOL_COST, "Retrofit Design Tool")
    except Exception as e:
        print(f"Credit deduction error: {e}")
    
    # Clear session
    if user_id in SESSION_STORAGE:
        del SESSION_STORAGE[user_id]
    
    buffer.seek(0)
    
    return Response(
        content=buffer.read(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=retrofit_design_{datetime.now().strftime('%Y%m%d')}.pdf"
        }
    )
