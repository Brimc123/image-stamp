"""
Retrofit Design Tool - COMPLETE WORKING VERSION
Restoring from October 19th working state + Measure Sheet fallback
"""

import io
import re
import json
from datetime import datetime
from typing import Dict, List, Optional
import PyPDF2
from fastapi import UploadFile
from fastapi.responses import HTMLResponse, Response
from openpyxl import load_workbook

# =============================================================================
# MEASURE DEFINITIONS
# =============================================================================

MEASURES = {
    "loft_insulation": {"name": "Loft Insulation", "icon": "🏠", "needs_calc": False},
    "cavity_wall": {"name": "Cavity Wall Insulation", "icon": "🧱", "needs_calc": False},
    "internal_wall": {"name": "Internal Wall Insulation", "icon": "🧱", "needs_calc": False},
    "room_in_roof": {"name": "Room in Roof", "icon": "🏠", "needs_calc": False},
    "solar_pv": {"name": "Solar PV", "icon": "☀️", "needs_calc": True},
    "heat_pump": {"name": "Air Source Heat Pump", "icon": "♨️", "needs_calc": True},
    "electric_storage": {"name": "Electric Storage Heaters", "icon": "🔌", "needs_calc": True},
    "gas_boiler": {"name": "Gas Boiler", "icon": "🔥", "needs_calc": False},
    "controls_prt": {"name": "Programmable Room Thermostat", "icon": "🌡️", "needs_calc": False},
    "controls_trv": {"name": "Thermostatic Radiator Valves", "icon": "🎚️", "needs_calc": False}
}

# Question definitions for each measure
MEASURE_QUESTIONS = {
    "loft_insulation": [
        {"id": "current_depth", "label": "Current loft insulation depth (mm)", "type": "number", "default": 0},
        {"id": "new_depth", "label": "New loft insulation depth (mm)", "type": "number", "default": 300},
        {"id": "area", "label": "Loft area (m²)", "type": "number", "default": 0}
    ],
    "solar_pv": [
        {"id": "system_size", "label": "System size (kWp)", "type": "number", "default": 0},
        {"id": "panel_count", "label": "Number of panels", "type": "number", "default": 0},
        {"id": "annual_generation", "label": "Estimated annual generation (kWh)", "type": "number", "default": 0}
    ],
    "heat_pump": [
        {"id": "capacity", "label": "Heat pump capacity (kW)", "type": "number", "default": 0},
        {"id": "scop", "label": "SCOP rating", "type": "number", "default": 0},
        {"id": "manufacturer", "label": "Manufacturer", "type": "text", "default": ""}
    ]
}

# =============================================================================
# PDF EXTRACTION
# =============================================================================

def extract_text_from_pdf(pdf_file: UploadFile) -> str:
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_file.file.read()))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        return text
    except:
        return ""

def extract_property_data(text: str) -> Dict:
    data = {}
    patterns = {
        "address": r"(?:Property Address|Address)[:\s]+([^\n]+)",
        "postcode": r"([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})",
        "property_type": r"(?:Property Type|Type)[:\s]+([^\n]+)",
        "floor_area": r"(?:Floor Area|Total.*Area)[:\s]+(\d+(?:\.\d+)?)\s*m",
        "loft_area": r"(?:Loft Area|Roof)[:\s]+(\d+(?:\.\d+)?)\s*m"
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data[key] = match.group(1).strip()
    return data

def extract_calc_data(text: str, calc_type: str) -> Dict:
    data = {}
    if calc_type == "solar":
        patterns = {
            "system_size": r"(?:System Size|Capacity)[:\s]+(\d+(?:\.\d+)?)",
            "panel_count": r"(?:Number of Panels|Panel Count)[:\s]+(\d+)",
            "annual_generation": r"(?:Annual Generation|Yearly Output)[:\s]+(\d+(?:,\d+)?)"
        }
    elif calc_type == "heat_pump":
        patterns = {
            "capacity": r"(?:Capacity|Output)[:\s]+(\d+(?:\.\d+)?)\s*kW",
            "scop": r"(?:SCOP|Efficiency)[:\s]+(\d+(?:\.\d+)?)"
        }
    elif calc_type == "esh":
        patterns = {
            "heater_count": r"(?:Number of Heaters|Heater Count)[:\s]+(\d+)",
            "total_capacity": r"(?:Total Capacity|Total Output)[:\s]+(\d+(?:\.\d+)?)"
        }
    else:
        return data
    
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).replace(',', '')
            data[key] = value
    return data

def extract_measure_sheet_data(file: UploadFile) -> Dict:
    try:
        wb = load_workbook(filename=io.BytesIO(file.file.read()))
        ws = wb.active
        data = {}
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[0] and row[1]:
                data[str(row[0]).strip()] = str(row[1]).strip()
        return data
    except:
        return {}

# =============================================================================
# SESSION STORAGE (Simple dict for now - use Redis in production)
# =============================================================================

_sessions = {}

def store_session_data(user_id: int, data: dict):
    _sessions[user_id] = data

def get_session_data(user_id: int) -> dict:
    return _sessions.get(user_id, {})

# =============================================================================
# HTML PAGES
# =============================================================================

def get_retrofit_tool_page():
    """Phase 1: Upload page"""
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Retrofit Design Tool - Upload</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }}
            .container {{ max-width: 1000px; margin: 0 auto; }}
            .header {{ text-align: center; color: white; margin-bottom: 30px; }}
            .header h1 {{ font-size: 32px; margin-bottom: 10px; }}
            .card {{
                background: white;
                border-radius: 16px;
                padding: 30px;
                margin-bottom: 20px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            }}
            .section-title {{
                font-size: 20px;
                font-weight: 600;
                margin-bottom: 20px;
                display: flex;
                align-items: center;
                gap: 10px;
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
            .format-name {{ font-weight: 700; font-size: 18px; margin-bottom: 8px; }}
            .upload-box {{
                border: 2px dashed #cbd5e0;
                border-radius: 12px;
                padding: 24px;
                text-align: center;
                cursor: pointer;
                transition: all 0.3s;
                margin-bottom: 20px;
            }}
            .upload-box:hover {{ border-color: #667eea; background: #f0f4ff; }}
            .upload-box.has-file {{ border-color: #48bb78; background: #f0fff4; }}
            .input-group {{ margin-bottom: 20px; }}
            .input-group label {{ display: block; margin-bottom: 8px; font-weight: 600; }}
            .input-group input {{
                width: 100%;
                padding: 12px;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                font-size: 14px;
            }}
            .measure-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
                gap: 15px;
                margin-bottom: 20px;
            }}
            .measure-card {{
                border: 2px solid #e0e0e0;
                border-radius: 12px;
                padding: 20px;
                text-align: center;
                cursor: pointer;
                transition: all 0.3s;
            }}
            .measure-card:hover {{ border-color: #667eea; }}
            .measure-card.selected {{ border-color: #667eea; background: #f0f4ff; }}
            .measure-icon {{ font-size: 36px; margin-bottom: 8px; }}
            .measure-name {{ font-size: 14px; font-weight: 600; }}
            .btn {{
                width: 100%;
                padding: 16px;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                transition: all 0.3s;
            }}
            .btn:hover {{ transform: translateY(-2px); box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4); }}
            .btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
            input[type="file"] {{ display: none; }}
            .info-banner {{
                background: #eef2ff;
                border-left: 4px solid #667eea;
                padding: 16px;
                border-radius: 8px;
                margin-bottom: 20px;
                font-size: 14px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🏠 Retrofit Design Tool</h1>
                <p>Generate PAS 2035 compliant retrofit designs</p>
            </div>
            
            <form id="mainForm" enctype="multipart/form-data">
                <!-- Format Selection -->
                <div class="card">
                    <div class="section-title">📋 Select Output Format</div>
                    <div class="format-grid">
                        <div class="format-card" onclick="selectFormat('elmhurst')">
                            <div class="format-icon">🏛️</div>
                            <div class="format-name">Elmhurst Style</div>
                            <div class="format-desc">Traditional format</div>
                        </div>
                        <div class="format-card" onclick="selectFormat('pas_hub')">
                            <div class="format-icon">⚡</div>
                            <div class="format-name">PAS Hub Style</div>
                            <div class="format-desc">Modern format</div>
                        </div>
                    </div>
                    <input type="hidden" name="format_style" id="formatStyle">
                </div>

                <!-- File Uploads -->
                <div class="card">
                    <div class="info-banner">
                        <strong>📊 Data Priority:</strong> 🔵 Site Notes → 🟢 Calc PDFs → 🟡 Measure Sheet (fallback)
                    </div>
                    
                    <div class="section-title">📄 Required Documents</div>
                    
                    <div class="upload-box" id="siteNotesBox" onclick="document.getElementById('siteNotes').click()">
                        <div>📄 Site Notes PDF</div>
                        <div id="siteNotesName"></div>
                    </div>
                    <input type="file" id="siteNotes" name="site_notes" accept=".pdf" required>
                    
                    <div class="upload-box" id="conditionBox" onclick="document.getElementById('conditionReport').click()">
                        <div>📄 Condition Report PDF</div>
                        <div id="conditionName"></div>
                    </div>
                    <input type="file" id="conditionReport" name="condition_report" accept=".pdf" required>
                </div>

                <!-- Optional Measure Sheet -->
                <div class="card">
                    <div class="section-title">📊 Optional Fallback Data</div>
                    <div class="upload-box" id="measureBox" onclick="document.getElementById('measureSheet').click()">
                        <div>📊 Measure Info Sheet (Excel) - OPTIONAL</div>
                        <div id="measureName"></div>
                    </div>
                    <input type="file" id="measureSheet" name="measure_sheet" accept=".xlsx,.xls">
                </div>

                <!-- Project Info -->
                <div class="card">
                    <div class="section-title">📝 Project Information</div>
                    <div class="input-group">
                        <label>Project Name</label>
                        <input type="text" name="project_name" required>
                    </div>
                    <div class="input-group">
                        <label>Coordinator Name</label>
                        <input type="text" name="coordinator" required>
                    </div>
                </div>

                <!-- Measure Selection -->
                <div class="card">
                    <div class="section-title">🔧 Select Measures</div>
                    <div class="measure-grid" id="measureGrid"></div>
                </div>

                <button type="submit" class="btn" id="submitBtn" disabled>Continue to Questions →</button>
            </form>
        </div>

        <script>
            let selectedFormat = '';
            let selectedMeasures = new Set();

            // Populate measures
            const measures = {json.dumps(MEASURES)};
            const grid = document.getElementById('measureGrid');
            Object.entries(measures).forEach(([id, info]) => {{
                const card = document.createElement('div');
                card.className = 'measure-card';
                card.innerHTML = `
                    <div class="measure-icon">${{info.icon}}</div>
                    <div class="measure-name">${{info.name}}</div>
                `;
                card.onclick = () => toggleMeasure(id, card);
                grid.appendChild(card);
            }});

            function selectFormat(format) {{
                selectedFormat = format;
                document.getElementById('formatStyle').value = format;
                document.querySelectorAll('.format-card').forEach(c => c.classList.remove('selected'));
                event.currentTarget.classList.add('selected');
                checkForm();
            }}

            function toggleMeasure(id, card) {{
                if (selectedMeasures.has(id)) {{
                    selectedMeasures.delete(id);
                    card.classList.remove('selected');
                }} else {{
                    selectedMeasures.add(id);
                    card.classList.add('selected');
                }}
                checkForm();
            }}

            function setupUpload(inputId, boxId, nameId) {{
                const input = document.getElementById(inputId);
                const box = document.getElementById(boxId);
                const status = document.getElementById(nameId);
                
                input.onchange = () => {{
                    if (input.files[0]) {{
                        status.textContent = '✓ ' + input.files[0].name;
                        box.classList.add('has-file');
                        checkForm();
                    }}
                }};
            }}

            function checkForm() {{
                const hasFormat = selectedFormat !== '';
                const hasSiteNotes = document.getElementById('siteNotes').files.length > 0;
                const hasCondition = document.getElementById('conditionReport').files.length > 0;
                const hasMeasures = selectedMeasures.size > 0;
                document.getElementById('submitBtn').disabled = !(hasFormat && hasSiteNotes && hasCondition && hasMeasures);
            }}

            setupUpload('siteNotes', 'siteNotesBox', 'siteNotesName');
            setupUpload('conditionReport', 'conditionBox', 'conditionName');
            setupUpload('measureSheet', 'measureBox', 'measureName');

            document.getElementById('mainForm').onsubmit = async (e) => {{
                e.preventDefault();
                const formData = new FormData(e.target);
                formData.append('selected_measures', JSON.stringify([...selectedMeasures]));
                
                try {{
                    const response = await fetch('/api/retrofit-process', {{
                        method: 'POST',
                        body: formData
                    }});
                    const result = await response.json();
                    if (result.success) {{
                        window.location.href = result.redirect;
                    }}
                }} catch (error) {{
                    alert('Error: ' + error.message);
                }}
            }};
        </script>
    </body>
    </html>
    """)

def get_calc_upload_page(session_data: Dict):
    """Phase 2: Calc upload page"""
    selected = session_data.get('selected_measures', [])
    needs_calcs = [m for m in selected if MEASURES.get(m, {}).get('needs_calc', False)]
    
    if not needs_calcs:
        return HTMLResponse('<script>window.location.href="/tool/retrofit/questions";</script>')
    
    upload_boxes = ""
    for measure_id in needs_calcs:
        info = MEASURES[measure_id]
        upload_boxes += f"""
        <div class="upload-box" onclick="document.getElementById('{measure_id}_calc').click()">
            <div>{info['icon']} {info['name']} Calculation</div>
            <div id="{measure_id}_name"></div>
        </div>
        <input type="file" id="{measure_id}_calc" name="{measure_id}_calc" accept=".pdf">
        """
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Upload Calculations</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }}
            .container {{ max-width: 800px; margin: 0 auto; }}
            .header {{ text-align: center; color: white; margin-bottom: 30px; }}
            .card {{
                background: white;
                border-radius: 16px;
                padding: 30px;
                margin-bottom: 20px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            }}
            .upload-box {{
                border: 2px dashed #cbd5e0;
                border-radius: 12px;
                padding: 24px;
                text-align: center;
                cursor: pointer;
                transition: all 0.3s;
                margin-bottom: 20px;
            }}
            .upload-box:hover {{ border-color: #667eea; background: #f0f4ff; }}
            .upload-box.has-file {{ border-color: #48bb78; background: #f0fff4; }}
            .btn {{
                width: 100%;
                padding: 16px;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }}
            input[type="file"] {{ display: none; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📊 Upload Calculations</h1>
                <p>Upload calculation PDFs for automatic data extraction</p>
            </div>
            
            <form id="calcForm" enctype="multipart/form-data">
                <div class="card">
                    {upload_boxes}
                </div>
                <button type="submit" class="btn">Continue to Questions →</button>
            </form>
        </div>

        <script>
            document.getElementById('calcForm').onsubmit = async (e) => {{
                e.preventDefault();
                const formData = new FormData(e.target);
                
                try {{
                    const response = await fetch('/api/retrofit-calcs', {{
                        method: 'POST',
                        body: formData
                    }});
                    const result = await response.json();
                    if (result.success) {{
                        window.location.href = result.redirect;
                    }}
                }} catch (error) {{
                    alert('Error: ' + error.message);
                }}
            }};
        </script>
    </body>
    </html>
    """)

def get_retrofit_questions_page(session_data: Dict):
    """Phase 3: Questions page"""
    selected = session_data.get('selected_measures', [])
    current_index = session_data.get('current_measure_index', 0)
    
    if current_index >= len(selected):
        return HTMLResponse('<script>window.location.href="/tool/retrofit/review";</script>')
    
    measure_id = selected[current_index]
    measure_info = MEASURES[measure_id]
    questions = MEASURE_QUESTIONS.get(measure_id, [])
    
    # Auto-populate from session data
    extracted = session_data.get('extracted_data', {})
    calc_data = session_data.get('calc_data', {})
    measure_sheet = session_data.get('measure_sheet_data', {})
    
    questions_html = ""
    for q in questions:
        # Try to auto-populate
        value = q['default']
        source = "none"
        
        # Priority 1: Extracted data
        if q['id'] in extracted:
            value = extracted[q['id']]
            source = "site_notes"
        # Priority 2: Calc data
        elif q['id'] in calc_data:
            value = calc_data[q['id']]
            source = "calc_pdf"
        # Priority 3: Measure sheet
        elif q['label'] in measure_sheet:
            value = measure_sheet[q['label']]
            source = "measure_sheet"
        
        badge = ""
        if source == "site_notes":
            badge = '<span style="background:#dbeafe;color:#1e40af;padding:4px 12px;border-radius:12px;font-size:12px">🔵 Site Notes</span>'
        elif source == "calc_pdf":
            badge = '<span style="background:#d1fae5;color:#065f46;padding:4px 12px;border-radius:12px;font-size:12px">🟢 Calc PDF</span>'
        elif source == "measure_sheet":
            badge = '<span style="background:#fef3c7;color:#92400e;padding:4px 12px;border-radius:12px;font-size:12px">🟡 Measure Sheet</span>'
        
        questions_html += f"""
        <div style="margin-bottom:20px">
            <label style="display:block;margin-bottom:8px;font-weight:600">{q['label']}</label>
            {badge}
            <input type="{q['type']}" name="{q['id']}" value="{value}" 
                   style="width:100%;padding:12px;border:2px solid #e0e0e0;border-radius:8px;margin-top:8px">
        </div>
        """
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Measure Questions</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }}
            .container {{ max-width: 800px; margin: 0 auto; }}
            .header {{ text-align: center; color: white; margin-bottom: 30px; }}
            .card {{
                background: white;
                border-radius: 16px;
                padding: 30px;
                margin-bottom: 20px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            }}
            .btn {{
                width: 100%;
                padding: 16px;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{measure_info['icon']} {measure_info['name']}</h1>
                <p>Question {current_index + 1} of {len(selected)}</p>
            </div>
            
            <form id="questionForm">
                <div class="card">
                    {questions_html}
                </div>
                <button type="submit" class="btn">Next →</button>
            </form>
        </div>

        <script>
            document.getElementById('questionForm').onsubmit = async (e) => {{
                e.preventDefault();
                const formData = new FormData(e.target);
                const answers = {{}};
                formData.forEach((value, key) => answers[key] = value);
                
                try {{
                    const response = await fetch('/api/retrofit-answer', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{answers}})
                    }});
                    const result = await response.json();
                    if (result.success) {{
                        window.location.href = result.redirect;
                    }}
                }} catch (error) {{
                    alert('Error: ' + error.message);
                }}
            }};
        </script>
    </body>
    </html>
    """)

def get_retrofit_review_page(session_data: Dict):
    """Phase 4: Review page"""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Review & Generate</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container { max-width: 800px; margin: 0 auto; }
            .header { text-align: center; color: white; margin-bottom: 30px; }
            .card {
                background: white;
                border-radius: 16px;
                padding: 30px;
                margin-bottom: 20px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            }
            .btn {
                width: 100%;
                padding: 16px;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>✅ Review & Generate PDF</h1>
                <p>All questions complete - ready to generate!</p>
            </div>
            
            <div class="card">
                <p>Your retrofit design is ready to be generated.</p>
                <p style="margin-top:10px">Click below to generate your PAS 2035 compliant PDF.</p>
            </div>

            <button class="btn" onclick="generatePDF()">Generate PDF →</button>
        </div>

        <script>
            async function generatePDF() {
                try {
                    const response = await fetch('/tool/retrofit/complete', {
                        method: 'POST'
                    });
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'retrofit-design.pdf';
                    a.click();
                } catch (error) {
                    alert('Error: ' + error.message);
                }
            }
        </script>
    </body>
    </html>
    """)

# =============================================================================
# BACKEND ROUTES (for main.py)
# =============================================================================

async def post_retrofit_process(request):
    """Process Phase 1 uploads"""
    try:
        form = await request.form()
        user_id = 1  # Get from session in production
        
        # Extract PDFs
        site_notes = form.get('site_notes')
        condition = form.get('condition_report')
        measure_sheet = form.get('measure_sheet')
        
        site_notes_text = extract_text_from_pdf(site_notes)
        condition_text = extract_text_from_pdf(condition)
        extracted_data = extract_property_data(site_notes_text + condition_text)
        
        measure_sheet_data = {}
        if measure_sheet:
            measure_sheet_data = extract_measure_sheet_data(measure_sheet)
        
        # Store session
        session_data = {
            "format_style": form.get('format_style'),
            "project_name": form.get('project_name'),
            "coordinator": form.get('coordinator'),
            "selected_measures": json.loads(form.get('selected_measures')),
            "extracted_data": extracted_data,
            "measure_sheet_data": measure_sheet_data,
            "current_measure_index": 0,
            "answers": {},
            "calc_data": {}
        }
        
        store_session_data(user_id, session_data)
        
        return Response(
            content=json.dumps({"success": True, "redirect": "/tool/retrofit/calcs"}),
            media_type="application/json"
        )
    except Exception as e:
        return Response(
            content=json.dumps({"success": False, "error": str(e)}),
            media_type="application/json",
            status_code=500
        )

async def post_retrofit_calcs(request):
    """Process Phase 2 calc uploads"""
    try:
        form = await request.form()
        user_id = 1
        session_data = get_session_data(user_id)
        
        calc_data = {}
        for measure_id in session_data['selected_measures']:
            calc_file = form.get(f'{measure_id}_calc')
            if calc_file:
                text = extract_text_from_pdf(calc_file)
                calc_type = "solar" if "solar" in measure_id else "heat_pump" if "heat" in measure_id else "esh"
                calc_data.update(extract_calc_data(text, calc_type))
        
        session_data['calc_data'] = calc_data
        store_session_data(user_id, session_data)
        
        return Response(
            content=json.dumps({"success": True, "redirect": "/tool/retrofit/questions"}),
            media_type="application/json"
        )
    except Exception as e:
        return Response(
            content=json.dumps({"success": False, "error": str(e)}),
            media_type="application/json",
            status_code=500
        )

async def post_retrofit_answer(request):
    """Process Phase 3 answers"""
    try:
        data = await request.json()
        user_id = 1
        session_data = get_session_data(user_id)
        
        current_index = session_data['current_measure_index']
        measure_id = session_data['selected_measures'][current_index]
        
        if 'answers' not in session_data:
            session_data['answers'] = {}
        session_data['answers'][measure_id] = data['answers']
        session_data['current_measure_index'] += 1
        
        store_session_data(user_id, session_data)
        
        # Check if more questions
        if session_data['current_measure_index'] >= len(session_data['selected_measures']):
            redirect = "/tool/retrofit/review"
        else:
            redirect = "/tool/retrofit/questions"
        
        return Response(
            content=json.dumps({"success": True, "redirect": redirect}),
            media_type="application/json"
        )
    except Exception as e:
        return Response(
            content=json.dumps({"success": False, "error": str(e)}),
            media_type="application/json",
            status_code=500
        )
