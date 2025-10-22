"""
RETROFIT DESIGN TOOL - COMPLETE FIXED VERSION
✅ FIX 1: Improved loft extraction from site notes
✅ FIX 2: ASHP extraction from measure sheet
✅ FIX 3: Drag-and-drop for calc uploads
✅ FIX 4: JSON parsing error fixed
"""

import io
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
    address_match = re.search(r'(?:Property Address|Address)[:\s]+(.*?)(?:\n|Postcode)', text, re.IGNORECASE | re.DOTALL)
    if address_match:
        data['address'] = address_match.group(1).strip().replace('\n', ', ')
    
    # Postcode
    postcode_match = re.search(r'(?:Postcode|Post Code)[:\s]+([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})', text, re.IGNORECASE)
    if postcode_match:
        data['postcode'] = postcode_match.group(1).strip()
    
    # Property type
    prop_type_match = re.search(r'(?:Property Type|Type of Property)[:\s]+(.*?)(?:\n|$)', text, re.IGNORECASE)
    if prop_type_match:
        data['property_type'] = prop_type_match.group(1).strip()
    
    # Wall construction
    wall_match = re.search(r'(?:Wall[s]?\s*[-]?\s*Construction Type|Construction Type)[:\s]+(.*?)(?:\n|$)', text, re.IGNORECASE)
    if wall_match:
        data['wall_type'] = wall_match.group(1).strip()
    
    # Build date
    date_match = re.search(r'(?:Build Date|Age Range|Construction Date)[:\s]+(\d{4}[-\s]?\d{0,4})', text, re.IGNORECASE)
    if date_match:
        data['build_date'] = date_match.group(1).strip()
    
    # ✅ IMPROVED LOFT EXTRACTION
    # Pattern 1: "Roofs - Insulation Thickness: 100 mm"
    loft_thickness_match = re.search(r'(?:Roofs?\s*[-]?\s*Insulation Thickness|Insulation Thickness)[:\s]+(\d+)\s*mm', text, re.IGNORECASE)
    if loft_thickness_match:
        data['loft_current_depth'] = loft_thickness_match.group(1)
    
    # Pattern 2: "Existing Loft insulation Thickness 100"
    if 'loft_current_depth' not in data:
        loft_existing_match = re.search(r'Existing Loft insulation Thickness[:\s]+(\d+)', text, re.IGNORECASE)
        if loft_existing_match:
            data['loft_current_depth'] = loft_existing_match.group(1)
    
    # Loft area - Multiple patterns
    # Pattern 1: "M2 Area being treated 18.24"
    loft_area_match = re.search(r'(?:LOFT.*?M2 Area being treated|Loft Area)[:\s]+(\d+\.?\d*)', text, re.IGNORECASE | re.DOTALL)
    if loft_area_match:
        data['loft_area'] = loft_area_match.group(1)
    
    # Pattern 2: "Area (m2)" from building measurements
    if 'loft_area' not in data:
        area_match = re.search(r'Extension 1.*?Floor 0[:\s]+(\d+\.?\d*)', text, re.IGNORECASE | re.DOTALL)
        if area_match:
            data['loft_area'] = area_match.group(1)
    
    return data

def extract_measure_sheet_data(excel_file: UploadFile) -> Dict:
    """✅ IMPROVED: Extract data from measure sheet Excel - ENHANCED ASHP EXTRACTION"""
    data = {}
    try:
        wb = openpyxl.load_workbook(io.BytesIO(excel_file.file.read()))
        sheet = wb.active
        
        current_measure = None
        
        for row in sheet.iter_rows(values_only=True):
            if not row or not row[0]:
                continue
            
            cell_value = str(row[0]).strip().upper()
            
            # Detect measure headers
            if cell_value in ["LOFT", "ESH", "PRT", "TRV", "GAS BOILER", "HEAT PUMP", "SOLAR PV", "IWI", "CWI", "RIR"]:
                current_measure = cell_value.replace(" ", "_")
                if current_measure not in data:
                    data[current_measure] = {}
                continue
            
            if current_measure and len(row) >= 2:
                field_name = str(row[0]).strip()
                field_value = str(row[1]).strip() if row[1] else ""
                
                # Map fields to question IDs
                if current_measure == "LOFT":
                    if "M2 Area" in field_name or "Area being treated" in field_name:
                        data[current_measure]['area'] = field_value
                    elif "Existing" in field_name and "Thickness" in field_name:
                        data[current_measure]['current_depth'] = field_value
                
                elif current_measure == "HEAT_PUMP":
                    # ✅ ENHANCED EXTRACTION FOR HEAT PUMP
                    if "Make and model" in field_name or "Make" in field_name:
                        data[current_measure]['make_model'] = field_value
                    elif "size" in field_name.lower() and "kw" in field_name.lower():
                        # Extract number from "Heat pump size req (KW) 8"
                        size_match = re.search(r'(\d+\.?\d*)', field_value)
                        if size_match:
                            data[current_measure]['capacity'] = size_match.group(1)
                        else:
                            data[current_measure]['capacity'] = field_value
                    elif "Heat Demand Calculator" in field_name:
                        data[current_measure]['heat_calc'] = "Yes" if field_value.upper() in ["Y", "YES"] else "No"
                    elif "SCOP" in field_name:
                        data[current_measure]['scop'] = field_value
                
                elif current_measure == "SOLAR_PV":
                    if "Make and model" in field_name:
                        data[current_measure]['make_model'] = field_value
                    elif "System size" in field_name:
                        data[current_measure]['system_size'] = field_value
                    elif "Calculations included" in field_name:
                        data[current_measure]['calcs_included'] = "Yes" if field_value.upper() in ["Y", "YES"] else "No"
                
                elif current_measure == "ESH":
                    if "Manufacturer" in field_name:
                        data[current_measure]['manufacturer'] = field_value
                    elif "Model" in field_name:
                        data[current_measure]['model'] = field_value
                    elif "Heat Demand" in field_name:
                        data[current_measure]['heat_calc'] = "Yes" if field_value.upper() in ["Y", "YES"] else "No"
                
                elif current_measure == "PRT":
                    if "Make and model" in field_name:
                        data[current_measure]['make_model'] = field_value
                
                elif current_measure == "TRV":
                    if "Make and model" in field_name:
                        data[current_measure]['make_model'] = field_value
                    elif "Number of TRV" in field_name:
                        data[current_measure]['quantity'] = field_value
        
        wb.close()
    except Exception as e:
        print(f"Measure sheet extraction error: {e}")
    
    return data

def parse_calculation_file(text: str, calc_type: str) -> Dict:
    """Parse calculation PDFs for Solar/Heat Pump/ESH"""
    data = {}
    
    if calc_type == "solar":
        # System size
        size_match = re.search(r'(?:System size|Total System Size|kWp)[:\s]+(\d+\.?\d*)\s*kW', text, re.IGNORECASE)
        if size_match:
            data['system_size'] = size_match.group(1)
        
        # Panel details
        panel_match = re.search(r'(?:Panel|Module)[:\s]+(.*?)(?:\n|$)', text, re.IGNORECASE)
        if panel_match:
            data['make_model'] = panel_match.group(1).strip()
    
    elif calc_type == "heatpump":
        # Capacity
        capacity_match = re.search(r'(?:Capacity|Size|Output)[:\s]+(\d+\.?\d*)\s*kW', text, re.IGNORECASE)
        if capacity_match:
            data['capacity'] = capacity_match.group(1)
        
        # SCOP
        scop_match = re.search(r'SCOP[:\s]+(\d+\.?\d*)', text, re.IGNORECASE)
        if scop_match:
            data['scop'] = scop_match.group(1)
        
        # Manufacturer
        manu_match = re.search(r'(?:Manufacturer|Make)[:\s]+(.*?)(?:\n|$)', text, re.IGNORECASE)
        if manu_match:
            data['make_model'] = manu_match.group(1).strip()
    
    elif calc_type == "esh":
        # Manufacturer
        manu_match = re.search(r'Manufacturer[:\s]+(.*?)(?:\n|$)', text, re.IGNORECASE)
        if manu_match:
            data['manufacturer'] = manu_match.group(1).strip()
        
        # Model
        model_match = re.search(r'Model[:\s]+(.*?)(?:\n|$)', text, re.IGNORECASE)
        if model_match:
            data['model'] = model_match.group(1).strip()
    
    return data

# ============================================================================
# PHASE 1: UPLOAD & MEASURE SELECTION
# ============================================================================

def get_retrofit_tool_page(request: Request):
    """Phase 1: Upload site notes and select measures"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    user_id = user_row["id"]
    credits = float(user_row.get("credits", 0.0))
    
    # Build measure cards HTML
    measure_cards = ""
    for measure_code, measure_info in MEASURES.items():
        measure_cards += f"""
        <div class="measure-card" onclick="toggleMeasure('{measure_code}')">
            <input type="checkbox" id="measure_{measure_code}" name="measures" value="{measure_code}" style="display:none;">
            <div class="measure-icon">{measure_info['icon']}</div>
            <div class="measure-name">{measure_info['name']}</div>
            {'<div class="calc-badge">Requires Calc</div>' if measure_info['requires_calc'] else ''}
        </div>
        """
    
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
            background: rgba(255, 255, 255, 0.95);
            padding: 20px 40px;
            border-radius: 15px;
            margin-bottom: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }}
        .header h1 {{ color: #333; font-size: 28px; }}
        .credits {{ background: #10b981; color: white; padding: 10px 20px; border-radius: 25px; font-weight: 600; }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }}
        .section-title {{
            font-size: 22px;
            font-weight: 700;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
            color: #333;
        }}
        .format-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }}
        .format-card {{
            border: 3px solid #e0e0e0;
            border-radius: 12px;
            padding: 30px 20px;
            cursor: pointer;
            text-align: center;
            transition: all 0.3s;
        }}
        .format-card:hover {{ border-color: #667eea; transform: translateY(-2px); }}
        .format-card.selected {{ border-color: #667eea; background: #f0f4ff; }}
        .format-icon {{ font-size: 48px; margin-bottom: 12px; }}
        .format-name {{ font-weight: 700; font-size: 18px; color: #333; }}
        .upload-box {{
            border: 2px dashed #cbd5e0;
            border-radius: 12px;
            padding: 40px 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
            margin-bottom: 20px;
            position: relative;
        }}
        .upload-box:hover {{ border-color: #667eea; background: #f0f4ff; }}
        .upload-box.has-file {{ border-color: #48bb78; background: #f0fff4; }}
        .upload-box.dragover {{ border-color: #667eea; background: #e0e7ff; transform: scale(1.02); }}
        .upload-icon {{ font-size: 48px; margin-bottom: 10px; }}
        .upload-text {{ font-size: 16px; color: #666; margin-bottom: 5px; }}
        .upload-subtext {{ font-size: 14px; color: #999; }}
        .file-name {{ color: #48bb78; font-weight: 600; margin-top: 10px; }}
        .input-group {{ margin-bottom: 20px; }}
        .input-group label {{ display: block; margin-bottom: 8px; font-weight: 600; color: #333; }}
        .input-group input, .input-group textarea {{
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
        }}
        .input-group input:focus, .input-group textarea:focus {{
            outline: none;
            border-color: #667eea;
        }}
        .measures-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        .measure-card {{
            border: 2px solid #e0e0e0;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
            position: relative;
        }}
        .measure-card:hover {{ border-color: #667eea; transform: translateY(-2px); }}
        .measure-card.selected {{ border-color: #667eea; background: #f0f4ff; }}
        .measure-icon {{ font-size: 40px; margin-bottom: 10px; }}
        .measure-name {{ font-size: 14px; font-weight: 600; color: #333; }}
        .calc-badge {{
            position: absolute;
            top: 5px;
            right: 5px;
            background: #f59e0b;
            color: white;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 600;
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
        .btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
        input[type="file"] {{ display: none; }}
        .cost-badge {{
            background: #fef3c7;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
            font-weight: 600;
            margin-bottom: 20px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🗂️ Retrofit Design Tool</h1>
        <div class="credits">£{credits:.2f}</div>
    </div>
    
    <div class="container">
        <div class="cost-badge">💰 Cost: £{RETROFIT_TOOL_COST:.2f} per design document</div>
        
        <form id="retrofitForm" method="POST" action="/tool/retrofit/process" enctype="multipart/form-data">
            
            <!-- Format Selection -->
            <div class="section-title">📋 Step 1: Select Site Notes Format</div>
            <div class="format-grid">
                <div class="format-card" onclick="selectFormat('PAS Hub')">
                    <input type="radio" name="format_style" value="PAS Hub" id="format_pashub" required style="display:none;">
                    <div class="format-icon">📘</div>
                    <div class="format-name">PAS Hub</div>
                </div>
                <div class="format-card" onclick="selectFormat('Elmhurst')">
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
            
            <!-- Measure Selection -->
            <div class="section-title">🔧 Step 4: Select Measures</div>
            <div class="measures-grid">
                {measure_cards}
            </div>
            
            <button type="submit" class="btn" id="submitBtn">Continue to Questions →</button>
        </form>
    </div>
    
    <script>
        function selectFormat(format) {{
            document.querySelectorAll('.format-card').forEach(card => card.classList.remove('selected'));
            event.currentTarget.classList.add('selected');
            if (format === 'PAS Hub') {{
                document.getElementById('format_pashub').checked = true;
            }} else {{
                document.getElementById('format_elmhurst').checked = true;
            }}
        }}
        
        function toggleMeasure(code) {{
            const checkbox = document.getElementById('measure_' + code);
            const card = event.currentTarget;
            checkbox.checked = !checkbox.checked;
            card.classList.toggle('selected');
        }}
        
        // Drag and drop functionality
        function setupDragDrop(boxId, inputId, nameId) {{
            const box = document.getElementById(boxId);
            const input = document.getElementById(inputId);
            const nameDiv = document.getElementById(nameId);
            
            ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {{
                box.addEventListener(eventName, preventDefaults, false);
            }});
            
            function preventDefaults(e) {{
                e.preventDefault();
                e.stopPropagation();
            }}
            
            ['dragenter', 'dragover'].forEach(eventName => {{
                box.addEventListener(eventName, () => box.classList.add('dragover'), false);
            }});
            
            ['dragleave', 'drop'].forEach(eventName => {{
                box.addEventListener(eventName, () => box.classList.remove('dragover'), false);
            }});
            
            box.addEventListener('drop', function(e) {{
                const dt = e.dataTransfer;
                const files = dt.files;
                input.files = files;
                handleFiles(files, boxId, nameId);
            }});
            
            input.addEventListener('change', function(e) {{
                handleFiles(e.target.files, boxId, nameId);
            }});
            
            function handleFiles(files, boxId, nameId) {{
                if (files.length > 0) {{
                    const fileName = files[0].name;
                    document.getElementById(nameId).textContent = '✓ ' + fileName;
                    document.getElementById(boxId).classList.add('has-file');
                }}
            }}
        }}
        
        setupDragDrop('siteNotesBox', 'siteNotes', 'siteNotesName');
        setupDragDrop('conditionBox', 'conditionReport', 'conditionName');
        setupDragDrop('measureBox', 'measureSheet', 'measureName');
        
        // Form validation
        document.getElementById('retrofitForm').addEventListener('submit', function(e) {{
            const measures = document.querySelectorAll('input[name="measures"]:checked');
            if (measures.length === 0) {{
                e.preventDefault();
                alert('Please select at least one measure');
                return false;
            }}
        }});
    </script>
</body>
</html>
    """
    return HTMLResponse(html)

async def post_retrofit_process(request: Request):
    """✅ FIXED: Process Phase 1 uploads and extract data"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    user_id = user_row["id"]
    
    try:
        form = await request.form()
        
        # Extract uploaded files
        site_notes = form.get("site_notes")
        condition_report = form.get("condition_report")
        measure_sheet = form.get("measure_sheet")
        
        # Read PDFs
        site_notes_bytes = await site_notes.read()
        condition_bytes = await condition_report.read()
        
        site_notes_text = extract_text_from_pdf(site_notes_bytes)
        condition_text = extract_text_from_pdf(condition_bytes)
        
        # Extract property data
        extracted_data = extract_property_data(site_notes_text + "\n" + condition_text)
        
        # Extract measure sheet data if provided
        measure_sheet_data = {}
        if measure_sheet and hasattr(measure_sheet, 'filename') and measure_sheet.filename:
            measure_sheet_data = extract_measure_sheet_data(measure_sheet)
        
        # ✅ FIX: Get selected measures correctly from form
        selected_measures = form.getlist("measures")
        
        # Store session data
        session_data = {
            "format_style": form.get("format_style"),
            "project_name": form.get("project_name"),
            "coordinator": form.get("coordinator"),
            "selected_measures": selected_measures,
            "extracted_data": extracted_data,
            "measure_sheet_data": measure_sheet_data,
            "current_measure_index": 0,
            "answers": {},
            "calc_data": {}
        }
        
        store_session_data(user_id, session_data)
        
        # Check if any measures require calculations
        requires_calcs = any(MEASURES[m]['requires_calc'] for m in selected_measures)
        
        if requires_calcs:
            return RedirectResponse("/tool/retrofit/calcs", status_code=303)
        else:
            return RedirectResponse("/tool/retrofit/questions", status_code=303)
        
    except Exception as e:
        print(f"Error in post_retrofit_process: {e}")
        return HTMLResponse(f"<h1>Error</h1><p>{str(e)}</p><a href='/tool/retrofit'>Back</a>")

# ============================================================================
# PHASE 2: CALCULATION UPLOADS - ✅ WITH DRAG-AND-DROP
# ============================================================================

def get_calc_upload_page(request: Request):
    """✅ Phase 2 with drag-and-drop functionality"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    user_id = user_row["id"]
    session_data = get_session_data(user_id)
    
    if not session_data:
        return RedirectResponse("/tool/retrofit", status_code=303)
    
    selected_measures = session_data.get("selected_measures", [])
    measures_needing_calcs = [m for m in selected_measures if MEASURES[m]['requires_calc']]
    
    if not measures_needing_calcs:
        return RedirectResponse("/tool/retrofit/questions", status_code=303)
    
    # Build upload boxes for each measure
    upload_boxes = ""
    for measure_code in measures_needing_calcs:
        measure_info = MEASURES[measure_code]
        upload_boxes += f"""
        <div class="upload-box" id="calc{measure_code}Box" onclick="document.getElementById('calc{measure_code}').click()">
            <div class="upload-icon">{measure_info['icon']}</div>
            <div class="upload-text">{measure_info['name']} Calculations</div>
            <div class="upload-subtext">Drag & drop PDF or click to browse (Optional)</div>
            <div class="file-name" id="calc{measure_code}Name"></div>
        </div>
        <input type="file" id="calc{measure_code}" name="calc_{measure_code}" accept=".pdf">
        """
    
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Upload Calculations - Retrofit Tool</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }}
        h1 {{ color: #333; margin-bottom: 10px; text-align: center; }}
        .subtitle {{ text-align: center; color: #666; margin-bottom: 30px; }}
        .upload-box {{
            border: 2px dashed #cbd5e0;
            border-radius: 12px;
            padding: 40px 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
            margin-bottom: 20px;
        }}
        .upload-box:hover {{ border-color: #667eea; background: #f0f4ff; }}
        .upload-box.has-file {{ border-color: #48bb78; background: #f0fff4; }}
        .upload-box.dragover {{ border-color: #667eea; background: #e0e7ff; transform: scale(1.02); }}
        .upload-icon {{ font-size: 48px; margin-bottom: 10px; }}
        .upload-text {{ font-size: 18px; font-weight: 600; color: #333; margin-bottom: 5px; }}
        .upload-subtext {{ font-size: 14px; color: #999; }}
        .file-name {{ color: #48bb78; font-weight: 600; margin-top: 10px; }}
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
            margin-top: 20px;
        }}
        .btn:hover {{ transform: scale(1.02); }}
        input[type="file"] {{ display: none; }}
        .info-box {{
            background: #e3f2fd;
            border-left: 4px solid #2196f3;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Upload Calculation Files</h1>
        <p class="subtitle">Optional: Upload calculation PDFs to auto-populate technical data</p>
        
        <div class="info-box">
            💡 <strong>Tip:</strong> If you don't have calculation files, you can skip this step and enter data manually in the next step.
        </div>
        
        <form id="calcForm" method="POST" action="/tool/retrofit/calcs" enctype="multipart/form-data">
            {upload_boxes}
            <button type="submit" class="btn">Continue to Questions →</button>
        </form>
    </div>
    
    <script>
        // Setup drag-and-drop for each upload box
        {chr(10).join([f"setupDragDrop('calc{m}Box', 'calc{m}', 'calc{m}Name');" for m in measures_needing_calcs])}
        
        function setupDragDrop(boxId, inputId, nameId) {{
            const box = document.getElementById(boxId);
            const input = document.getElementById(inputId);
            const nameDiv = document.getElementById(nameId);
            
            ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {{
                box.addEventListener(eventName, preventDefaults, false);
            }});
            
            function preventDefaults(e) {{
                e.preventDefault();
                e.stopPropagation();
            }}
            
            ['dragenter', 'dragover'].forEach(eventName => {{
                box.addEventListener(eventName, () => box.classList.add('dragover'), false);
            }});
            
            ['dragleave', 'drop'].forEach(eventName => {{
                box.addEventListener(eventName, () => box.classList.remove('dragover'), false);
            }});
            
            box.addEventListener('drop', function(e) {{
                const dt = e.dataTransfer;
                const files = dt.files;
                input.files = files;
                handleFiles(files, boxId, nameId);
            }});
            
            input.addEventListener('change', function(e) {{
                handleFiles(e.target.files, boxId, nameId);
            }});
            
            function handleFiles(files, boxId, nameId) {{
                if (files.length > 0) {{
                    const fileName = files[0].name;
                    document.getElementById(nameId).textContent = '✓ ' + fileName;
                    document.getElementById(boxId).classList.add('has-file');
                }}
            }}
        }}
    </script>
</body>
</html>
    """
    return HTMLResponse(html)

async def post_calc_upload(request: Request):
    """Process calculation file uploads"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    user_id = user_row["id"]
    session_data = get_session_data(user_id)
    
    if not session_data:
        return RedirectResponse("/tool/retrofit", status_code=303)
    
    try:
        form = await request.form()
        calc_data = {}
        
        for measure_code in session_data.get("selected_measures", []):
            calc_file = form.get(f"calc_{measure_code}")
            if calc_file and hasattr(calc_file, 'filename') and calc_file.filename:
                calc_bytes = await calc_file.read()
                calc_text = extract_text_from_pdf(calc_bytes)
                
                # Determine calc type
                if measure_code == "SOLAR_PV":
                    calc_type = "solar"
                elif measure_code == "HEAT_PUMP":
                    calc_type = "heatpump"
                elif measure_code == "ESH":
                    calc_type = "esh"
                else:
                    continue
                
                extracted = parse_calculation_file(calc_text, calc_type)
                if extracted:
                    calc_data[measure_code] = extracted
        
        session_data['calc_data'] = calc_data
        store_session_data(user_id, session_data)
        
        return RedirectResponse("/tool/retrofit/questions", status_code=303)
        
    except Exception as e:
        print(f"Error in post_calc_upload: {e}")
        return RedirectResponse("/tool/retrofit/questions", status_code=303)

# ============================================================================
# PHASE 3: QUESTIONS WITH AUTO-POPULATION
# ============================================================================

def get_questions_page(request: Request):
    """Phase 3: Show questions with 3-tier auto-population"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    user_id = user_row["id"]
    session_data = get_session_data(user_id)
    
    if not session_data:
        return RedirectResponse("/tool/retrofit", status_code=303)
    
    selected_measures = session_data.get("selected_measures", [])
    current_index = session_data.get("current_measure_index", 0)
    
    if current_index >= len(selected_measures):
        return RedirectResponse("/tool/retrofit/download", status_code=303)
    
    current_measure_code = selected_measures[current_index]
    current_measure = MEASURES[current_measure_code]
    
    # Build questions HTML with auto-population
    questions_html = ""
    for question in current_measure['questions']:
        q_id = question['id']
        
        # 3-TIER AUTO-POPULATION
        value = ""
        source = ""
        
        # Tier 1: Site Notes (highest priority)
        site_key = f"{current_measure_code.lower()}_{q_id}"
        if site_key in session_data.get("extracted_data", {}):
            value = session_data["extracted_data"][site_key]
            source = "🔵 Site Notes"
        
        # Tier 2: Calculation PDFs
        if not value and current_measure_code in session_data.get("calc_data", {}):
            if q_id in session_data["calc_data"][current_measure_code]:
                value = session_data["calc_data"][current_measure_code][q_id]
                source = "🟢 Calculations"
        
        # Tier 3: Measure Sheet (fallback)
        if not value and current_measure_code in session_data.get("measure_sheet_data", {}):
            if q_id in session_data["measure_sheet_data"][current_measure_code]:
                value = session_data["measure_sheet_data"][current_measure_code][q_id]
                source = "🟡 Measure Sheet"
        
        # Default value if still empty
        if not value and 'default' in question:
            value = question['default']
        
        source_badge = f'<span class="source-badge">{source}</span>' if source else ''
        
        if question['type'] == 'select':
            options_html = "".join([f'<option value="{opt}" {"selected" if str(value)==opt else ""}>{opt}</option>' 
                                   for opt in question.get('options', [])])
            questions_html += f"""
            <div class="input-group">
                <label>{question['label']} {source_badge}</label>
                <select name="{q_id}" required>
                    <option value="">Select...</option>
                    {options_html}
                </select>
            </div>
            """
        else:
            input_type = question['type']
            questions_html += f"""
            <div class="input-group">
                <label>{question['label']} {source_badge}</label>
                <input type="{input_type}" name="{q_id}" value="{value}" required>
            </div>
            """
    
    progress = ((current_index + 1) / len(selected_measures)) * 100
    
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Questions - Retrofit Tool</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }}
        .progress-bar {{
            height: 8px;
            background: #e0e0e0;
            border-radius: 4px;
            margin-bottom: 30px;
            overflow: hidden;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            transition: width 0.3s;
        }}
        .measure-header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .measure-icon {{ font-size: 60px; margin-bottom: 10px; }}
        .measure-title {{ font-size: 24px; font-weight: 700; color: #333; margin-bottom: 5px; }}
        .measure-subtitle {{ color: #666; }}
        .input-group {{
            margin-bottom: 20px;
        }}
        .input-group label {{
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #333;
        }}
        .input-group input, .input-group select, .input-group textarea {{
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
        }}
        .input-group input:focus, .input-group select:focus {{
            outline: none;
            border-color: #667eea;
        }}
        .source-badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            margin-left: 8px;
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
    </style>
</head>
<body>
    <div class="container">
        <div class="progress-bar">
            <div class="progress-fill" style="width: {progress}%"></div>
        </div>
        
        <div class="measure-header">
            <div class="measure-icon">{current_measure['icon']}</div>
            <div class="measure-title">{current_measure['name']}</div>
            <div class="measure-subtitle">Measure {current_index + 1} of {len(selected_measures)}</div>
        </div>
        
        <form method="POST" action="/tool/retrofit/answer">
            <input type="hidden" name="measure_code" value="{current_measure_code}">
            {questions_html}
            <button type="submit" class="btn">
                {'Next Measure →' if current_index < len(selected_measures) - 1 else 'Generate Design →'}
            </button>
        </form>
    </div>
</body>
</html>
    """
    return HTMLResponse(html)

async def post_questions_submit(request: Request):
    """Process question answers"""
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
# PHASE 4 & 5: GENERATE PDF
# ============================================================================

def get_pdf_download(request: Request):
    """Generate and download PDF"""
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
    story.append(Paragraph("Retrofit Design Document", title_style))
    
    # Project info
    story.append(Paragraph(f"<b>Project:</b> {session_data.get('project_name', 'N/A')}", styles['Normal']))
    story.append(Paragraph(f"<b>Coordinator:</b> {session_data.get('coordinator', 'N/A')}", styles['Normal']))
    story.append(Paragraph(f"<b>Format:</b> {session_data.get('format_style', 'N/A')}", styles['Normal']))
    story.append(Spacer(1, 0.3*inch))
    
    # Selected measures heading
    story.append(Paragraph("<b>Selected Measures</b>", styles['Heading2']))
    story.append(Spacer(1, 0.2*inch))
    
    # Each measure
    for measure_code in session_data.get("selected_measures", []):
        measure = MEASURES[measure_code]
        answers = session_data.get("answers", {}).get(measure_code, {})
        
        story.append(Paragraph(f"<b>{measure['name']}</b>", styles['Heading3']))
        
        for key, value in answers.items():
            if key != "measure_code":
                story.append(Paragraph(f"• <b>{key}:</b> {value}", styles['Normal']))
        
        story.append(Spacer(1, 0.2*inch))
    
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
