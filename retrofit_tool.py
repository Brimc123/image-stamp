"""
RETROFIT DESIGN TOOL - FIXED DATA EXTRACTION
✅ Fixed extraction for Easy PV format (Solar)
✅ Fixed extraction for ecoProCAL format (ESH)
✅ Fixed extraction for SMART EPC format (Site Notes)
✅ All imports corrected
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
    # Map measure codes to generic filenames
    filename_mapping = {
        "HEAT_PUMP": "Heat_Pump.txt",
        "CWI": "Cavity_Wall_Insulation.txt", 
        "ESH": "Electric_Storage_Heaters.txt",
        "IWI": "Internal_Wall_Insulation.txt",
        "LOFT": "Loft_Insulation.txt",
        "PRT": "Heating_Controls.txt",
        "RIR": "Room_in_Roof_Insulation.txt",
        "SOLAR_PV": "Solar_PV.txt",
        "TRV": "Heating_Controls.txt",
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
        return f"Error loading installation instructions: {str(e)}"

# ============================================================================
# DATA EXTRACTION FUNCTIONS - FIXED FOR YOUR PDF FORMATS
# ============================================================================

def parse_calculation_file(text: str, calc_type: str) -> Dict:
    """Parse calculation PDFs for ESSENTIAL info only - full PDFs will be attached to design"""
    data = {}
    
    if calc_type == "solar":
        # System size - match Easy PV format: "Installed capacity of PV system – kWp (stc): 3.690 kWp"
        size_patterns = [
            r'Installed capacity of PV system[^\d]*(\d+\.?\d*)\s*kWp',  # Easy PV format
            r'System size[:\s]+(\d+\.?\d*)\s*kW',
            r'Total.*?(\d+\.?\d*)\s*kWp'
        ]
        for pattern in size_patterns:
            size_match = re.search(pattern, text, re.IGNORECASE)
            if size_match:
                data['system_size'] = size_match.group(1)
                break
        
        # Extract panel info: "9 Anglo Solar solar panels"
        panel_patterns = [
            r'Input \d+:\s*(\d+)\s+([^,\n]+?)\s+solar panels',  # Easy PV: "Input 1: 9 Anglo Solar solar panels"
            r'(\d+)\s*x\s*([^\n]+?)\s+panels?',
            r'Panel.*?:\s*([^\n]+)'
        ]
        for pattern in panel_patterns:
            panel_match = re.search(pattern, text, re.IGNORECASE)
            if panel_match:
                if len(panel_match.groups()) == 2:
                    count, model = panel_match.groups()
                    data['panel_count'] = count
                    data['panel_model'] = model.strip()
                break
        
        # Extract inverter: "Growat MIN 3.6kW 1ph Hybrid"
        inverter_patterns = [
            r'(Growat[^\n]+)',
            r'(SolaX[^\n]+)',
            r'Inverter[^\n]*:\s*([^\n]+)',
            r'([\w\s]+\d+\.?\d*\s*kW[^\n]+inverter)'
        ]
        for pattern in inverter_patterns:
            inv_match = re.search(pattern, text, re.IGNORECASE)
            if inv_match:
                data['inverter_model'] = inv_match.group(1).strip()
                break
        
        # Create combined make/model description
        if 'panel_count' in data and 'panel_model' in data and 'inverter_model' in data:
            data['make_model'] = f"{data['panel_count']}x {data['panel_model']} with {data['inverter_model']}"
        elif 'panel_model' in data and 'inverter_model' in data:
            data['make_model'] = f"{data['panel_model']} with {data['inverter_model']}"
    
    elif calc_type == "heatpump":
        # Capacity
        capacity_match = re.search(r'(?:Capacity|Size|Output)[:\s]+(\d+\.?\d*)\s*kW', text, re.IGNORECASE)
        if capacity_match:
            data['capacity'] = capacity_match.group(1)
        
        # Manufacturer and model
        manuf_match = re.search(r'Manufacturer[:\s]+([\w\s]+)', text, re.IGNORECASE)
        model_match = re.search(r'Model[:\s]+([\w\-\/]+)', text, re.IGNORECASE)
        
        if manuf_match and model_match:
            data['make_model'] = f"{manuf_match.group(1).strip()} {model_match.group(1).strip()}"
        elif manuf_match:
            data['make_model'] = manuf_match.group(1).strip()
    
    elif calc_type == "esh":
        # ESH - Extract from ecoProCAL format
        # Pattern: "Room 1    Living Room 1    21°C    ... Primary Heaters : 1x Elnur ECOHHR30 PLUS/SOLAR"
        
        heater_info = []
        
        # Find all room entries with heater specifications
        room_patterns = [
            r'(Room \d+)\s+([^\d\n]+?)\s+\d+°C.*?Primary Heaters\s*:\s*(\d+x\s*[^\n]+)',  # ecoProCAL format
            r'(Room \d+).*?Heater.*?:\s*([^\n]+)',
        ]
        
        for pattern in room_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                room_num = match.group(1)
                if len(match.groups()) >= 3:
                    room_name = match.group(2).strip()
                    heater = match.group(3).strip()
                else:
                    room_name = ""
                    heater = match.group(2).strip()
                
                heater_info.append({
                    'room': room_num,
                    'room_name': room_name,
                    'heater': heater
                })
        
        if heater_info:
            data['heaters'] = heater_info
            # Create summary for make_model field
            heater_models = list(set([h['heater'] for h in heater_info]))
            data['make_model'] = ', '.join(heater_models)
    
    return data

def parse_site_notes(text: str) -> Dict:
    """Extract essential property info from site notes (PAS Hub or Elmhurst)"""
    data = {}
    
    # Address - multiple patterns
    address_patterns = [
        r'Property Address:\s*([^\n]+)',  # PAS Hub
        r'Address:\s*([^\n]+)',
        r'Property:\s*([^\n]+)'
    ]
    for pattern in address_patterns:
        addr_match = re.search(pattern, text, re.IGNORECASE)
        if addr_match:
            data['address'] = addr_match.group(1).strip()
            break
    
    # Postcode
    postcode_match = re.search(r'Postcode[:\s]+([A-Z]{1,2}\d{1,2}\s?\d[A-Z]{2})', text, re.IGNORECASE)
    if postcode_match:
        data['postcode'] = postcode_match.group(1)
    
    # Property Type
    prop_type_patterns = [
        r'Type of Property:\s*([^\n]+)',
        r'Property type:\s*([^\n]+)',
        r'Detachment Type:\s*([^\n]+)'
    ]
    for pattern in prop_type_patterns:
        type_match = re.search(pattern, text, re.IGNORECASE)
        if type_match:
            data['property_type'] = type_match.group(1).strip()
            break
    
    # Build Date / Age
    age_patterns = [
        r'Age Range:\s*(\d{4}\s*-\s*\d{4})',
        r'Date Built:\s*([^\n]+)',
        r'Construction.*?(\d{4})'
    ]
    for pattern in age_patterns:
        age_match = re.search(pattern, text, re.IGNORECASE)
        if age_match:
            data['build_date'] = age_match.group(1).strip()
            break
    
    # Wall Construction
    wall_patterns = [
        r'Walls - Construction Type:\s*([^\n]+)',
        r'Wall.*?construction:\s*([^\n]+)',
        r'External Walls:\s*([^\n]+)'
    ]
    for pattern in wall_patterns:
        wall_match = re.search(pattern, text, re.IGNORECASE)
        if wall_match:
            data['wall_type'] = wall_match.group(1).strip()
            break
    
    # Floor Area - look in building measurements
    area_patterns = [
        r'Area.*?\(m2\)\s+(\d+)',  # Table format
        r'Floor area:\s*(\d+)',
        r'Total.*?area:\s*(\d+)'
    ]
    for pattern in area_patterns:
        area_match = re.search(pattern, text, re.IGNORECASE)
        if area_match:
            data['floor_area'] = area_match.group(1)
            break
    
    # Loft Insulation - improved patterns for "270 mm" format
    loft_patterns = [
        r'Roofs - Insulation Thickness:\s*(\d+)\s*mm',  # "270 mm"
        r'Loft insulation.*?(\d+)\s*mm',
        r'Roof.*?insulation.*?(\d+)\s*mm'
    ]
    for pattern in loft_patterns:
        loft_match = re.search(pattern, text, re.IGNORECASE)
        if loft_match:
            data['loft_thickness'] = loft_match.group(1)
            break
    
    # Heated Rooms Count
    rooms_patterns = [
        r'Heated.*?rooms?:\s*(\d+)',
        r'Number of habitable rooms:\s*(\d+)',
        r'Habitable.*?(\d+)'
    ]
    for pattern in rooms_patterns:
        rooms_match = re.search(pattern, text, re.IGNORECASE)
        if rooms_match:
            data['heated_rooms'] = rooms_match.group(1)
            break
    
    return data

def parse_measure_sheet(filepath: str) -> Dict:
    """Extract data from measure sheet Excel file"""
    data = {}
    
    try:
        wb = openpyxl.load_workbook(filepath)
        ws = wb.active
        
        current_measure = None
        
        for row in ws.iter_rows(values_only=True):
            if not row or not any(row):
                continue
            
            # Check if this row defines a measure
            if row[0] and str(row[0]).strip().upper() in ["LOFT", "CWI", "IWI", "RIR", "SOLAR_PV", "HEAT_PUMP", "ESH", "GAS_BOILER", "PRT", "TRV"]:
                current_measure = str(row[0]).strip().upper()
                if current_measure not in data:
                    data[current_measure] = {}
            
            # Extract field data
            if current_measure and len(row) >= 2:
                field_name = str(row[0]).strip() if row[0] else ""
                field_value = str(row[1]).strip() if row[1] else ""
                
                if not field_name or not field_value:
                    continue
                
                # Map common fields
                if current_measure == "LOFT":
                    if "Current depth" in field_name or "existing" in field_name.lower():
                        data[current_measure]['current_depth'] = field_value
                    elif "Top-up" in field_name or "additional" in field_name.lower():
                        data[current_measure]['topup_depth'] = field_value
                    elif "Total area" in field_name or "area" in field_name.lower():
                        data[current_measure]['area'] = field_value
                
                elif current_measure == "HEAT_PUMP":
                    if "Make and model" in field_name:
                        data[current_measure]['make_model'] = field_value
                    elif "Size" in field_name or "capacity" in field_name.lower():
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

# ============================================================================
# PDF GENERATION
# ============================================================================

def generate_retrofit_pdf(session_data: Dict) -> bytes:
    """Generate the retrofit design PDF with installation instructions"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#2C5F2D'),
        spaceAfter=12,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#2C5F2D'),
        spaceAfter=6,
        spaceBefore=12
    )
    
    body_style = styles['BodyText']
    body_style.fontSize = 10
    body_style.leading = 14
    
    story = []
    
    # Title Page
    story.append(Paragraph("RETROFIT DESIGN & INSTALLATION PLAN", title_style))
    story.append(Spacer(1, 0.3*inch))
    
    # Property Details
    story.append(Paragraph("Property Details", heading_style))
    story.append(Paragraph(f"<b>Project Name:</b> {session_data.get('project_name', 'N/A')}", body_style))
    story.append(Paragraph(f"<b>Coordinator:</b> {session_data.get('coordinator', 'N/A')}", body_style))
    story.append(Paragraph(f"<b>Format:</b> {session_data.get('format', 'N/A')}", body_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Section 1: Design Specifications
    story.append(PageBreak())
    story.append(Paragraph("SECTION 1: DESIGN SPECIFICATIONS", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    selected_measures = session_data.get('selected_measures', [])
    answers = session_data.get('answers', {})
    
    for measure in selected_measures:
        measure_answers = answers.get(measure, {})
        if measure_answers:
            story.append(Paragraph(f"Measure: {measure}", heading_style))
            
            for question, answer in measure_answers.items():
                story.append(Paragraph(f"<b>{question}:</b> {answer}", body_style))
            
            story.append(Spacer(1, 0.2*inch))
    
    # Section 2: Installation Instructions
    story.append(PageBreak())
    story.append(Paragraph("SECTION 2: INSTALLATION INSTRUCTIONS", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    for measure in selected_measures:
        story.append(Paragraph(f"{measure} - INSTALLATION PROCEDURE", heading_style))
        
        instructions = load_installation_instructions(measure)
        
        # Split instructions into paragraphs
        for para in instructions.split('\n\n'):
            if para.strip():
                story.append(Paragraph(para.strip().replace('\n', '<br/>'), body_style))
                story.append(Spacer(1, 0.1*inch))
        
        story.append(Spacer(1, 0.2*inch))
    
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# ============================================================================
# ROUTE FUNCTIONS
# ============================================================================

async def get_retrofit_tool_page(request: Request):
    """Phase 1: Upload & Measure Selection"""
    user_row = await require_active_user_row(request)
    
    # Available measures
    measures = [
        {"code": "LOFT", "name": "Loft Insulation", "icon": "🏠"},
        {"code": "CWI", "name": "Cavity Wall Insulation", "icon": "🧱"},
        {"code": "IWI", "name": "Internal Wall Insulation", "icon": "🏘️"},
        {"code": "RIR", "name": "Room in Roof", "icon": "🏠"},
        {"code": "SOLAR_PV", "name": "Solar PV", "icon": "☀️"},
        {"code": "HEAT_PUMP", "name": "Air Source Heat Pump", "icon": "🔥"},
        {"code": "ESH", "name": "Electric Storage Heater", "icon": "🔌"},
        {"code": "GAS_BOILER", "name": "Gas Boiler", "icon": "🔥"},
        {"code": "PRT", "name": "Programmable Room Thermostat", "icon": "🌡️"},
        {"code": "TRV", "name": "Thermostatic Radiator Valves", "icon": "🌡️"}
    ]
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Retrofit Design Tool</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }}
            h1 {{ color: #2C5F2D; }}
            .format-selection {{ display: flex; gap: 20px; margin: 20px 0; }}
            .format-card {{ flex: 1; padding: 20px; border: 2px solid #ddd; border-radius: 8px; cursor: pointer; }}
            .format-card.selected {{ border-color: #2C5F2D; background: #f0f8f0; }}
            .upload-zone {{ border: 2px dashed #ccc; padding: 40px; text-align: center; margin: 20px 0; border-radius: 8px; }}
            .measures-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
            .measure-card {{ padding: 15px; border: 2px solid #ddd; border-radius: 8px; cursor: pointer; text-align: center; }}
            .measure-card.selected {{ border-color: #2C5F2D; background: #f0f8f0; }}
            .btn {{ background: #2C5F2D; color: white; padding: 12px 30px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }}
            .btn:hover {{ background: #1d3f1e; }}
            input[type="text"] {{ width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 4px; }}
        </style>
    </head>
    <body>
        <h1>Retrofit Design Tool - Phase 1</h1>
        
        <form method="post" action="/tool/retrofit/process" enctype="multipart/form-data">
            <h2>1. Select Format</h2>
            <div class="format-selection">
                <div class="format-card" onclick="selectFormat('PAS Hub')">
                    <h3>PAS Hub</h3>
                    <p>SMART EPC format</p>
                    <input type="radio" name="format" value="PAS Hub" required>
                </div>
                <div class="format-card" onclick="selectFormat('Elmhurst')">
                    <h3>Elmhurst</h3>
                    <p>Elmhurst Energy format</p>
                    <input type="radio" name="format" value="Elmhurst" required>
                </div>
            </div>
            
            <h2>2. Project Information</h2>
            <input type="text" name="project_name" placeholder="Project Name" required>
            <input type="text" name="coordinator" placeholder="Coordinator Name" required>
            
            <h2>3. Upload Documents</h2>
            <div class="upload-zone">
                <label>Site Notes PDF (Required)</label><br>
                <input type="file" name="site_notes" accept=".pdf" required>
            </div>
            
            <div class="upload-zone">
                <label>Condition Report PDF (Required)</label><br>
                <input type="file" name="condition_report" accept=".pdf" required>
            </div>
            
            <div class="upload-zone">
                <label>Measure Sheet Excel (Optional)</label><br>
                <input type="file" name="measure_sheet" accept=".xlsx">
            </div>
            
            <h2>4. Select Measures</h2>
            <div class="measures-grid">
                {"".join([f'''
                <div class="measure-card" onclick="toggleMeasure('{m["code"]}')">
                    <div style="font-size: 40px;">{m["icon"]}</div>
                    <h4>{m["name"]}</h4>
                    <input type="checkbox" name="measures" value="{m["code"]}" id="measure_{m["code"]}">
                </div>
                ''' for m in measures])}
            </div>
            
            <button type="submit" class="btn">Continue →</button>
        </form>
        
        <script>
            function selectFormat(format) {{
                document.querySelectorAll('.format-card').forEach(card => card.classList.remove('selected'));
                event.currentTarget.classList.add('selected');
                event.currentTarget.querySelector('input[type="radio"]').checked = true;
            }}
            
            function toggleMeasure(code) {{
                const checkbox = document.getElementById('measure_' + code);
                checkbox.checked = !checkbox.checked;
                event.currentTarget.classList.toggle('selected', checkbox.checked);
            }}
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)

async def post_retrofit_process(request: Request):
    """Process Phase 1 uploads and move to Phase 2"""
    user_row = await require_active_user_row(request)
    
    form = await request.form()
    
    # Store session data
    session_id = str(user_row['id'])
    SESSION_STORAGE[session_id] = {
        'format': form.get('format'),
        'project_name': form.get('project_name'),
        'coordinator': form.get('coordinator'),
        'selected_measures': form.getlist('measures'),
        'extracted_data': {}
    }
    
    # Process uploaded files
    site_notes = form.get('site_notes')
    if site_notes:
        content = await site_notes.read()
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        
        site_data = parse_site_notes(text)
        SESSION_STORAGE[session_id]['extracted_data']['site_notes'] = site_data
    
    # Process measure sheet if provided
    measure_sheet = form.get('measure_sheet')
    if measure_sheet:
        content = await measure_sheet.read()
        temp_path = f"/tmp/{session_id}_measures.xlsx"
        with open(temp_path, 'wb') as f:
            f.write(content)
        
        measure_data = parse_measure_sheet(temp_path)
        SESSION_STORAGE[session_id]['extracted_data']['measure_sheet'] = measure_data
        
        os.remove(temp_path)
    
    # Check if calculations needed
    needs_calcs = any(m in SESSION_STORAGE[session_id]['selected_measures'] for m in ['SOLAR_PV', 'HEAT_PUMP', 'ESH'])
    
    if needs_calcs:
        return RedirectResponse(url="/tool/retrofit/calcs", status_code=303)
    else:
        return RedirectResponse(url="/tool/retrofit/questions", status_code=303)

async def get_calc_upload_page(request: Request):
    """Phase 2: Calculation uploads (conditional)"""
    user_row = await require_active_user_row(request)
    session_id = str(user_row['id'])
    
    if session_id not in SESSION_STORAGE:
        return RedirectResponse(url="/tool/retrofit", status_code=303)
    
    selected = SESSION_STORAGE[session_id]['selected_measures']
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Upload Calculations</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }}
            h1 {{ color: #2C5F2D; }}
            .upload-zone {{ border: 2px dashed #ccc; padding: 40px; text-align: center; margin: 20px 0; border-radius: 8px; }}
            .btn {{ background: #2C5F2D; color: white; padding: 12px 30px; border: none; border-radius: 5px; cursor: pointer; }}
        </style>
    </head>
    <body>
        <h1>Phase 2: Upload Calculations</h1>
        
        <form method="post" action="/tool/retrofit/calcs" enctype="multipart/form-data">
            {"".join([f'''
            <div class="upload-zone">
                <label>{measure} Calculations (Required)</label><br>
                <input type="file" name="{measure.lower()}_calc" accept=".pdf" required>
            </div>
            ''' for measure in selected if measure in ['SOLAR_PV', 'HEAT_PUMP', 'ESH']])}
            
            <button type="submit" class="btn">Continue →</button>
        </form>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)

async def post_calc_upload(request: Request):
    """Process calculation uploads"""
    user_row = await require_active_user_row(request)
    session_id = str(user_row['id'])
    
    form = await request.form()
    
    # Process each calculation file
    for measure in ['solar_pv', 'heat_pump', 'esh']:
        calc_file = form.get(f'{measure}_calc')
        if calc_file:
            content = await calc_file.read()
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text()
            
            calc_data = parse_calculation_file(text, measure.replace('_', ''))
            SESSION_STORAGE[session_id]['extracted_data'][f'{measure}_calc'] = calc_data
    
    return RedirectResponse(url="/tool/retrofit/questions", status_code=303)

async def get_questions_page(request: Request):
    """Phase 3: Questions with auto-population"""
    user_row = await require_active_user_row(request)
    session_id = str(user_row['id'])
    
    if session_id not in SESSION_STORAGE:
        return RedirectResponse(url="/tool/retrofit", status_code=303)
    
    session = SESSION_STORAGE[session_id]
    selected_measures = session.get('selected_measures', [])
    
    if not selected_measures:
        return RedirectResponse(url="/tool/retrofit/download", status_code=303)
    
    current_measure = selected_measures[0]
    
    # Get questions for this measure (simplified for now)
    questions = {
        'SOLAR_PV': ['System size (kW)', 'Make and model being installed'],
        'HEAT_PUMP': ['Heat pump size req (KW)', 'Make and model being installed'],
        'ESH': ['Manufacturer', 'Model'],
        'LOFT': ['Current depth (mm)', 'Top-up depth (mm)', 'Total area (m2)'],
    }
    
    measure_questions = questions.get(current_measure, ['Question 1', 'Question 2'])
    
    # Auto-populate from extracted data
    extracted = session.get('extracted_data', {})
    prefilled = {}
    
    if current_measure == 'SOLAR_PV':
        solar_data = extracted.get('solarpv_calc', {})
        prefilled['System size (kW)'] = solar_data.get('system_size', '')
        prefilled['Make and model being installed'] = solar_data.get('make_model', '')
    
    elif current_measure == 'HEAT_PUMP':
        hp_data = extracted.get('heatpump_calc', {})
        prefilled['Heat pump size req (KW)'] = hp_data.get('capacity', '')
        prefilled['Make and model being installed'] = hp_data.get('make_model', '')
    
    elif current_measure == 'ESH':
        esh_data = extracted.get('esh_calc', {})
        prefilled['Manufacturer'] = esh_data.get('make_model', '').split()[0] if esh_data.get('make_model') else ''
        prefilled['Model'] = esh_data.get('make_model', '')
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Questions - {current_measure}</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
            h1 {{ color: #2C5F2D; }}
            .question {{ margin: 20px 0; }}
            input[type="text"] {{ width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; }}
            .btn {{ background: #2C5F2D; color: white; padding: 12px 30px; border: none; border-radius: 5px; cursor: pointer; }}
            .badge {{ background: #4CAF50; color: white; padding: 3px 8px; border-radius: 3px; font-size: 12px; }}
        </style>
    </head>
    <body>
        <h1>Questions for {current_measure}</h1>
        
        <form method="post" action="/tool/retrofit/answer">
            <input type="hidden" name="measure" value="{current_measure}">
            
            {"".join([f'''
            <div class="question">
                <label>{q}</label>
                {f'<span class="badge">Auto-populated</span>' if prefilled.get(q) else ''}
                <input type="text" name="{q}" value="{prefilled.get(q, '')}" required>
            </div>
            ''' for q in measure_questions])}
            
            <button type="submit" class="btn">Continue →</button>
        </form>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)

async def post_questions_submit(request: Request):
    """Save answers and move to next measure"""
    user_row = await require_active_user_row(request)
    session_id = str(user_row['id'])
    
    form = await request.form()
    measure = form.get('measure')
    
    # Save answers
    if 'answers' not in SESSION_STORAGE[session_id]:
        SESSION_STORAGE[session_id]['answers'] = {}
    
    SESSION_STORAGE[session_id]['answers'][measure] = {k: v for k, v in form.items() if k != 'measure'}
    
    # Remove this measure from the list
    SESSION_STORAGE[session_id]['selected_measures'].remove(measure)
    
    return RedirectResponse(url="/tool/retrofit/questions", status_code=303)

async def get_pdf_download(request: Request):
    """Phase 5: Generate and download PDF"""
    user_row = await require_active_user_row(request)
    session_id = str(user_row['id'])
    
    if session_id not in SESSION_STORAGE:
        return RedirectResponse(url="/tool/retrofit", status_code=303)
    
    # Deduct credits
    new_balance = update_user_credits(user_row['id'], -RETROFIT_TOOL_COST)
    add_transaction(user_row['id'], 'debit', RETROFIT_TOOL_COST, 'Retrofit Design Tool')
    
    # Generate PDF
    pdf_bytes = generate_retrofit_pdf(SESSION_STORAGE[session_id])
    
    # Clean up session
    del SESSION_STORAGE[session_id]
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=retrofit_design.pdf"}
    )
