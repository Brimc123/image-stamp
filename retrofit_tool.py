"""
Retrofit Design Tool - COMPLETE VERSION WITH FULL HTML
Phases 1-5: All HTML forms restored from Phase 3
"""

import io
import re
import json
from datetime import datetime
from typing import Dict, List, Optional
import PyPDF2
from fastapi import Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, Response, RedirectResponse

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# Import from your existing AutoDate modules
from auth import require_active_user_row
from database import update_user_credits, add_transaction

# Cost configuration
RETROFIT_TOOL_COST = 10.0  # £10 per design

# ==================== MEASURES CONFIGURATION ====================

MEASURES = {
    "LOFT": {
        "name": "Loft Insulation",
        "code": "LOFT",
        "icon": "🏠",
        "requires_calc": False,
        "questions": [
            {"id": "area", "label": "M2 Area being treated", "type": "number", "unit": "m²", "auto_populate": True},
            {"id": "existing", "label": "Existing Loft insulation Thickness", "type": "text", "auto_populate": True}
        ]
    },
    "ESH": {
        "name": "Electric Storage Heater",
        "code": "ESH",
        "icon": "🔌",
        "requires_calc": True,
        "questions": [
            {"id": "manufacturer", "label": "Manufacturer", "type": "text", "auto_populate": False},
            {"id": "calc", "label": "Heat Demand Calculator included Y/N?", "type": "yesno", "auto_populate": False},
            {"id": "model", "label": "Model numbers", "type": "text", "auto_populate": False}
        ]
    },
    "PRT": {
        "name": "Programmable Room Thermostat",
        "code": "PRT",
        "icon": "🌡️",
        "requires_calc": False,
        "questions": [
            {"id": "model", "label": "Make and model being installed", "type": "text", "auto_populate": False}
        ]
    },
    "TRV": {
        "name": "Thermostatic Radiator Valves",
        "code": "TRV",
        "icon": "🎚️",
        "requires_calc": False,
        "questions": [
            {"id": "model", "label": "Make and model being installed", "type": "text", "auto_populate": False},
            {"id": "quantity", "label": "Number of TRV's being installed", "type": "number", "auto_populate": True}
        ]
    },
    "GAS_BOILER": {
        "name": "Gas Boiler Replacement",
        "code": "GAS_BOILER",
        "icon": "🔥",
        "requires_calc": True,
        "questions": [
            {"id": "model", "label": "Make and model being installed", "type": "text", "auto_populate": False},
            {"id": "size", "label": "Boiler KW size req", "type": "number", "unit": "KW", "auto_populate": False},
            {"id": "calc", "label": "Heat Demand Calculator included Y/N?", "type": "yesno", "auto_populate": False}
        ]
    },
    "HEAT_PUMP": {
        "name": "Heat Pump",
        "code": "HEAT_PUMP",
        "icon": "♨️",
        "requires_calc": True,
        "questions": [
            {"id": "model", "label": "Make and model being installed", "type": "text", "auto_populate": False},
            {"id": "size", "label": "Heat pump size req (KW)", "type": "number", "unit": "KW", "auto_populate": False},
            {"id": "calc", "label": "Heat Demand Calculator included Y/N?", "type": "yesno", "auto_populate": False}
        ]
    },
    "SOLAR_PV": {
        "name": "Solar PV",
        "code": "SOLAR_PV",
        "icon": "☀️",
        "requires_calc": True,
        "questions": [
            {"id": "model", "label": "Make and model being installed", "type": "text", "auto_populate": False},
            {"id": "size", "label": "System size (KW)", "type": "number", "unit": "KW", "auto_populate": False},
            {"id": "calc", "label": "Solar PV Calculations included?", "type": "yesno", "auto_populate": False}
        ]
    },
    "IWI": {
        "name": "Internal Wall Insulation",
        "code": "IWI",
        "icon": "🗂️",
        "requires_calc": False,
        "questions": [
            {"id": "area", "label": "M2 Area being treated", "type": "number", "unit": "m²", "auto_populate": True},
            {"id": "omitted", "label": "Rooms being omitted from Install?", "type": "text", "auto_populate": False}
        ]
    },
    "CWI": {
        "name": "Cavity Wall Insulation",
        "code": "CWI",
        "icon": "🧱",
        "requires_calc": False,
        "questions": [
            {"id": "area", "label": "M2 Area being treated", "type": "number", "unit": "m²", "auto_populate": True},
            {"id": "width", "label": "Cavity width", "type": "text", "auto_populate": True},
            {"id": "product", "label": "CWI Product being used", "type": "text", "auto_populate": False}
        ]
    },
    "RIR": {
        "name": "Room in Roof",
        "code": "RIR",
        "icon": "🏠",
        "requires_calc": False,
        "questions": [
            {"id": "area", "label": "M2 Area being treated", "type": "number", "unit": "m²", "auto_populate": True}
        ]
    }
}

# ==================== HELPER FUNCTIONS ====================

def extract_text_from_pdf(pdf_file_bytes: bytes) -> str:
    """Extract text from PDF bytes"""
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_file_bytes))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        return text
    except Exception as e:
        raise Exception(f"Error reading PDF: {str(e)}")


def extract_data_from_text(site_notes_text: str, condition_report_text: str, format_type: str) -> Dict:
    """Extract property data from site notes"""
    combined_text = site_notes_text + " " + condition_report_text
    
    data = {
        "format": format_type,
        "address": "",
        "property_type": "",
        "build_date": "",
        "loft_area": 68,
        "loft_insulation": "100mm",
        "heated_rooms": 3,
        "cavity_width": "300mm",
        "wall_area": 68,
        "wall_type": "",
        "number_of_storeys": "1"
    }
    
    # ADDRESS
    postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})', combined_text, re.IGNORECASE)
    postcode = postcode_match.group(0).strip() if postcode_match else ""
    
    if format_type == "PAS Hub":
        address_match = re.search(r'Property Address:\s*(.+?)(?=\n\s*\n|\nProperty Photo|\nInspection Surveyor)', combined_text, re.IGNORECASE | re.DOTALL)
        if address_match:
            address_text = address_match.group(1).strip()
            address_lines = [line.strip().rstrip(',') for line in address_text.split('\n') if line.strip()]
            data["address"] = ', '.join(address_lines)
    else:
        address_match = re.search(r'(?:Property Address:|Address:)\s*(.+?)(?=\nPostcode:|\n\s*\n)', combined_text, re.IGNORECASE | re.MULTILINE)
        if address_match:
            address_text = address_match.group(1).strip()
            address_lines = [line.strip().rstrip(',') for line in address_text.split('\n') if line.strip()]
            data["address"] = ', '.join(address_lines)
            if postcode and postcode not in data["address"]:
                data["address"] += f', {postcode}'
    
    if not data["address"] and postcode:
        data["address"] = postcode
    
    # PROPERTY TYPE
    is_bungalow = bool(re.search(r'Bungalow', combined_text, re.IGNORECASE))
    if re.search(r'Semi.*?[Dd]etached', combined_text, re.IGNORECASE):
        data["property_type"] = "Semi-Detached Bungalow" if is_bungalow else "Semi-Detached House"
    elif re.search(r'Detached', combined_text, re.IGNORECASE):
        data["property_type"] = "Detached Bungalow" if is_bungalow else "Detached House"
    elif re.search(r'Terraced', combined_text, re.IGNORECASE):
        data["property_type"] = "Terraced House"
    elif re.search(r'Flat', combined_text, re.IGNORECASE):
        data["property_type"] = "Flat"
    elif is_bungalow:
        data["property_type"] = "Bungalow"
    
    # BUILD DATE
    age_range_match = re.search(r'(?:Age Range|Built)[:\s]+(19\d{2}|20\d{2})\s*-\s*(19\d{2}|20\d{2})', combined_text, re.IGNORECASE)
    if age_range_match:
        data["build_date"] = f"{age_range_match.group(1)} - {age_range_match.group(2)}"
    else:
        date_match = re.search(r'(?:Date Built|Age Range|Built)[:\s]+([0-9]{4})', combined_text, re.IGNORECASE)
        if date_match:
            data["build_date"] = date_match.group(1)
    
    # WALL TYPE
    if re.search(r'Timber\s+frame', combined_text, re.IGNORECASE):
        data["wall_type"] = "Timber Frame"
    elif re.search(r'Cavity', combined_text, re.IGNORECASE):
        data["wall_type"] = "Cavity Wall"
    elif re.search(r'Solid', combined_text, re.IGNORECASE):
        data["wall_type"] = "Solid Wall"
    
    # NUMBER OF STOREYS
    storey_match = re.search(r'(?:Number of storeys|Storeys)[:\s]+([0-9]+)', combined_text, re.IGNORECASE)
    if storey_match:
        data["number_of_storeys"] = storey_match.group(1)
    
    # FLOOR AREA
    area_match = re.search(r'(?:Area|Floor\s+0)[:\s]+([0-9]+(?:\.[0-9]+)?)\s*(?:m|m2|m²)?', combined_text, re.IGNORECASE)
    if area_match:
        data["loft_area"] = float(area_match.group(1))
        data["wall_area"] = float(area_match.group(1))
    
    # LOFT INSULATION
    if format_type == "PAS Hub":
        loft_match = re.search(r'(?:Roofs.*?Insulation Thickness|Insulation Thickness)[:\s]+([0-9]+)\s*mm', combined_text, re.IGNORECASE | re.DOTALL)
        if loft_match:
            data["loft_insulation"] = f"{loft_match.group(1)}mm"
    
    # HEATED ROOMS
    heated_rooms_match = re.search(r'(?:HEATED rooms|Heated Habitable Rooms)[:\s]+([0-9]+)', combined_text, re.IGNORECASE)
    if heated_rooms_match:
        data["heated_rooms"] = int(heated_rooms_match.group(1))
    
    # CAVITY WIDTH
    wall_thickness_match = re.search(r'Wall thickness[:\s]+([0-9]+)\s*mm', combined_text, re.IGNORECASE)
    if wall_thickness_match:
        data["cavity_width"] = f"{wall_thickness_match.group(1)}mm"
    
    return data


def parse_calculation_file(calc_text: str, calc_type: str) -> Dict:
    """Parse calculation PDFs"""
    if calc_type == 'heatpump':
        data = {"heatPumpSize": "", "manufacturer": "", "model": ""}
        capacity_match = re.search(r'Capacity.*?([0-9]+)\s*kW', calc_text, re.IGNORECASE) or re.search(r'([0-9]+)\s*kW', calc_text, re.IGNORECASE)
        if capacity_match:
            data["heatPumpSize"] = float(capacity_match.group(1))
        if not data["heatPumpSize"]:
            data["heatPumpSize"] = 16
        return data
        
    elif calc_type == 'solar':
        data = {
            "systemSize": "",
            "systemSizeNumeric": 0,
            "panels": {"manufacturer": "", "quantity": 0},
            "inverter": {"manufacturer": "", "model": "", "capacity": ""},
            "performance": {"annualGeneration": "", "selfConsumption": "", "gridIndependence": "", "shadingFactor": ""},
            "orientation": [],
            "pitch": "",
            "mounting": "",
            "components": []
        }
        
        size_match = re.search(r'Installed capacity.*?([0-9.]+)\s*kWp', calc_text, re.IGNORECASE)
        if size_match:
            data["systemSize"] = f"{size_match.group(1)} kWp"
            data["systemSizeNumeric"] = float(size_match.group(1))
        
        panel_match = re.search(r'([A-Z\s]+)\s+solar panel', calc_text, re.IGNORECASE)
        if panel_match:
            data["panels"]["manufacturer"] = panel_match.group(1).strip()
        
        panel_qty = re.search(r'(\d+)\s+[A-Z\s]+\s+solar panel', calc_text, re.IGNORECASE)
        if panel_qty:
            data["panels"]["quantity"] = int(panel_qty.group(1))
        
        return data
    
    return {}


def get_installation_requirements(measure_code: str) -> List[str]:
    """Get installation requirements"""
    requirements = {
        'LOFT': ['Ensure adequate loft access', 'Check ventilation', 'Install insulation to specified depth'],
        'CWI': ['Borescope survey', 'Check cavity width', 'Appropriate insulation material'],
        'IWI': ['Remove fixtures', 'Install vapor control layer', 'Address thermal bridging'],
        'TRV': ['Isolate heating system', 'Install TRVs on all radiators', 'Commission system'],
        'PRT': ['Position at 1.5m height', 'Avoid heat sources', 'Program appropriately'],
        'SOLAR_PV': ['Structural survey', 'Install mounting system', 'DC cabling', 'Register with DNO', 'MCS certificate'],
        'HEAT_PUMP': ['Confirm sizing', 'Position outdoor unit', 'Install buffer tank', 'Commission system', 'MCS registration'],
        'GAS_BOILER': ['Confirm sizing', 'Remove old boiler', 'Upgrade controls', 'Commission', 'Building Regs notification'],
        'ESH': ['Calculate heat loss', 'Install per manufacturer specs', 'Adequate electrical supply', 'Program controller'],
        'RIR': ['Check roof structure', 'Maintain ventilation gap', 'Ensure insulation continuity']
    }
    return requirements.get(measure_code, ['Follow manufacturer instructions', 'Ensure Building Regs compliance'])


def generate_pdf_design(design_doc: Dict) -> bytes:
    """Generate PDF design document"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.4*inch, bottomMargin=0.5*inch, leftMargin=0.65*inch, rightMargin=0.65*inch)
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Colors
    primary_blue = colors.HexColor('#0F172A')
    accent_blue = colors.HexColor('#3B82F6')
    accent_green = colors.HexColor('#10B981')
    light_bg = colors.HexColor('#F8FAFC')
    mid_bg = colors.HexColor('#E2E8F0')
    text_mid = colors.HexColor('#475569')
    
    # Styles
    title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=32, textColor=primary_blue, spaceAfter=6, alignment=TA_CENTER, fontName='Helvetica-Bold', leading=38)
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Title'], fontSize=26, textColor=primary_blue, spaceAfter=24, alignment=TA_CENTER, fontName='Helvetica-Bold', leading=32)
    h1_style = ParagraphStyle('H1', parent=styles['Heading1'], fontSize=20, textColor=primary_blue, spaceAfter=16, spaceBefore=20, fontName='Helvetica-Bold', leading=24)
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=10.5, textColor=text_mid, spaceAfter=10, leading=16, alignment=TA_LEFT)
    
    # COVER PAGE
    elements.append(Spacer(1, 1.2*inch))
    elements.append(Paragraph("RETROFIT DESIGN", title_style))
    elements.append(Paragraph("& INSTALLATION PLAN", subtitle_style))
    elements.append(Spacer(1, 0.35*inch))
    
    badge_text = f'<para align="center"><font size="13" color="{accent_green}">✓ PAS 2035:2023 COMPLIANT</font><br/><font size="13" color="{accent_green}">✓ TRUSTMARK READY</font></para>'
    elements.append(Paragraph(badge_text, body_style))
    elements.append(Spacer(1, 0.6*inch))
    
    prop = design_doc['property']
    prop_data = [
        ['PROPERTY ADDRESS', prop.get('address', 'Not specified')],
        ['PROPERTY TYPE', prop.get('property_type', 'Not specified')],
        ['BUILD DATE', prop.get('build_date', 'Not specified')],
        ['DATE GENERATED', datetime.now().strftime('%d %B %Y')]
    ]
    
    prop_table = Table(prop_data, colWidths=[2.3*inch, 4.2*inch])
    prop_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), primary_blue),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.white),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (1, 0), (1, -1), light_bg),
        ('GRID', (0, 0), (-1, -1), 1, mid_bg),
        ('BOX', (0, 0), (-1, -1), 2, primary_blue),
        ('LEFTPADDING', (0, 0), (-1, -1), 14),
        ('TOPPADDING', (0, 0), (-1, -1), 11),
    ]))
    elements.append(prop_table)
    
    measures_list = ', '.join([MEASURES[m]['name'] for m in [measure['code'] for measure in design_doc['measures']]])
    summary_text = f'<para align="center"><font size="11"><b>MEASURES INCLUDED ({len(design_doc["measures"])})</b></font><br/>{measures_list}</para>'
    elements.append(Paragraph(summary_text, body_style))
    elements.append(PageBreak())
    
    # MEASURES
    for idx, measure in enumerate(design_doc['measures'], 1):
        elements.append(Paragraph(f"{idx}. {measure['name'].upper()}", h1_style))
        
        spec_data = [['SPECIFICATION', 'VALUE']]
        for answer in measure['answers']:
            if answer['answer']:
                value_str = f"{answer['answer']} {answer.get('unit', '')}".strip()
                spec_data.append([answer['question'], value_str])
        
        if len(spec_data) > 1:
            spec_table = Table(spec_data, colWidths=[3.4*inch, 3.1*inch])
            spec_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), accent_blue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, mid_bg),
                ('BOX', (0, 0), (-1, -1), 1.5, accent_blue),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, light_bg]),
                ('LEFTPADDING', (0, 0), (-1, -1), 12),
                ('TOPPADDING', (0, 0), (-1, -1), 10),
            ]))
            elements.append(spec_table)
        
        elements.append(Spacer(1, 0.2*inch))
        install_reqs = get_installation_requirements(measure['code'])
        for req in install_reqs:
            elements.append(Paragraph(f'• {req}', body_style))
        
        if idx < len(design_doc['measures']):
            elements.append(PageBreak())
    
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


# ==================== FASTAPI ROUTES WITH COMPLETE HTML ====================

def get_retrofit_tool_page(request: Request):
    """Entry point - COMPLETE upload page with full HTML"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row

    try:
        has_access = user_row.get("retrofit_tool_access", 1) == 1
    except Exception:
        has_access = True

    if not has_access:
        return HTMLResponse("<h1>Access Denied</h1><a href='/'>Back</a>")

    try:
        credits = float(user_row.get("credits", 0.0))
    except Exception:
        credits = 0.0

    # COMPLETE HTML FROM PHASE 3
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Retrofit Design Tool - AutoDate</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8fafc; color: #0f172a; }}
        .header {{ background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: white; padding: 2rem; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        .header h1 {{ font-size: 2rem; margin-bottom: 0.5rem; }}
        .credits {{ background: #10b981; color: white; padding: 0.5rem 1rem; border-radius: 20px; display: inline-block; font-weight: 600; margin-top: 1rem; }}
        .container {{ max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }}
        .card {{ background: white; border-radius: 12px; padding: 2rem; margin-bottom: 2rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .section-title {{ font-size: 1.5rem; color: #0f172a; margin-bottom: 1.5rem; padding-bottom: 0.5rem; border-bottom: 3px solid #3b82f6; }}
        
        /* Upload Areas */
        .upload-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; margin-bottom: 2rem; }}
        .upload-box {{ border: 3px dashed #cbd5e1; border-radius: 12px; padding: 2rem; text-align: center; transition: all 0.3s; cursor: pointer; background: #f8fafc; }}
        .upload-box:hover {{ border-color: #3b82f6; background: #eff6ff; }}
        .upload-box.drag-over {{ border-color: #10b981; background: #ecfdf5; }}
        .upload-icon {{ font-size: 3rem; margin-bottom: 1rem; }}
        .upload-label {{ font-size: 1.1rem; font-weight: 600; color: #0f172a; margin-bottom: 0.5rem; }}
        .upload-hint {{ font-size: 0.9rem; color: #64748b; }}
        input[type="file"] {{ display: none; }}
        
        /* Project Info */
        .form-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem; }}
        .form-group {{ margin-bottom: 1rem; }}
        label {{ display: block; font-weight: 600; margin-bottom: 0.5rem; color: #0f172a; }}
        input[type="text"], input[type="date"] {{ width: 100%; padding: 0.75rem; border: 2px solid #e2e8f0; border-radius: 8px; font-size: 1rem; transition: border-color 0.3s; }}
        input:focus {{ outline: none; border-color: #3b82f6; }}
        
        /* Measures Grid */
        .measures-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 1rem; }}
        .measure-card {{ border: 2px solid #e2e8f0; border-radius: 12px; padding: 1.5rem; text-align: center; cursor: pointer; transition: all 0.3s; background: white; }}
        .measure-card:hover {{ border-color: #3b82f6; transform: translateY(-2px); box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        .measure-card.selected {{ border-color: #10b981; background: #ecfdf5; }}
        .measure-icon {{ font-size: 2.5rem; margin-bottom: 0.5rem; }}
        .measure-name {{ font-weight: 600; color: #0f172a; }}
        .measure-checkbox {{ display: none; }}
        
        /* Buttons */
        .btn {{ padding: 1rem 2rem; border: none; border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; transition: all 0.3s; }}
        .btn-primary {{ background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); color: white; }}
        .btn-primary:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4); }}
        .btn-primary:disabled {{ background: #cbd5e1; cursor: not-allowed; transform: none; }}
        .btn-secondary {{ background: #f1f5f9; color: #0f172a; }}
        .btn-secondary:hover {{ background: #e2e8f0; }}
        
        .file-status {{ margin-top: 1rem; padding: 0.5rem; border-radius: 6px; font-size: 0.9rem; }}
        .file-status.success {{ background: #d1fae5; color: #065f46; }}
        .file-status.error {{ background: #fee2e2; color: #991b1b; }}
        
        @media (max-width: 768px) {{
            .upload-grid, .form-row {{ grid-template-columns: 1fr; }}
            .measures-grid {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🏗️ Retrofit Design Tool</h1>
        <p>PAS 2035 Compliant Design Documents</p>
        <div class="credits">💳 Credits: £{credits:.2f}</div>
    </div>

    <div class="container">
        <form id="retrofitForm" method="POST" enctype="multipart/form-data">
            
            <!-- STEP 1: Upload Files -->
            <div class="card">
                <h2 class="section-title">Step 1: Upload Site Documents</h2>
                <div class="upload-grid">
                    <!-- PAS Hub -->
                    <div>
                        <div class="upload-box" id="pasUploadBox">
                            <div class="upload-icon">📄</div>
                            <div class="upload-label">PAS Hub Site Notes</div>
                            <div class="upload-hint">Click or drag PDF here</div>
                            <input type="file" id="pasFile" name="pas_file" accept=".pdf">
                        </div>
                        <div id="pasStatus" class="file-status" style="display:none;"></div>
                    </div>
                    
                    <!-- Elmhurst -->
                    <div>
                        <div class="upload-box" id="elmhurstUploadBox">
                            <div class="upload-icon">📄</div>
                            <div class="upload-label">Elmhurst Condition Report</div>
                            <div class="upload-hint">Click or drag PDF here</div>
                            <input type="file" id="elmhurstFile" name="elmhurst_file" accept=".pdf">
                        </div>
                        <div id="elmhurstStatus" class="file-status" style="display:none;"></div>
                    </div>
                </div>
            </div>

            <!-- STEP 2: Project Information -->
            <div class="card">
                <h2 class="section-title">Step 2: Project Information</h2>
                <div class="form-row">
                    <div class="form-group">
                        <label>Project Name</label>
                        <input type="text" name="project_name" required placeholder="e.g., Smith Residence Retrofit">
                    </div>
                    <div class="form-group">
                        <label>Retrofit Coordinator</label>
                        <input type="text" name="coordinator" required placeholder="Your name">
                    </div>
                </div>
                <div class="form-group">
                    <label>Property Address</label>
                    <input type="text" id="propertyAddress" name="property_address" required placeholder="Will auto-populate from documents">
                </div>
            </div>

            <!-- STEP 3: Select Measures -->
            <div class="card">
                <h2 class="section-title">Step 3: Select Retrofit Measures</h2>
                <div class="measures-grid" id="measuresGrid">
                    <!-- JavaScript will populate measures -->
                </div>
            </div>

            <!-- Submit Button -->
            <div class="card" style="text-align: center;">
                <button type="button" class="btn btn-primary" id="continueBtn" disabled>
                    Continue to Questions →
                </button>
                <a href="/" class="btn btn-secondary" style="display: inline-block; margin-left: 1rem; text-decoration: none;">
                    ← Back to Dashboard
                </a>
            </div>
        </form>
    </div>

    <script>
        // Measures data
        const measures = {json.dumps(MEASURES)};
        
        // State
        let selectedMeasures = new Set();
        let extractedData = null;
        
        // Populate measures grid
        const grid = document.getElementById('measuresGrid');
        Object.keys(measures).forEach(code => {{
            const m = measures[code];
            const card = document.createElement('div');
            card.className = 'measure-card';
            card.innerHTML = `
                <div class="measure-icon">${{m.icon}}</div>
                <div class="measure-name">${{m.name}}</div>
                <input type="checkbox" class="measure-checkbox" name="measures[]" value="${{code}}" id="m_${{code}}">
            `;
            card.onclick = () => toggleMeasure(code, card);
            grid.appendChild(card);
        }});
        
        function toggleMeasure(code, card) {{
            const checkbox = document.getElementById(`m_${{code}}`);
            checkbox.checked = !checkbox.checked;
            
            if (checkbox.checked) {{
                selectedMeasures.add(code);
                card.classList.add('selected');
            }} else {{
                selectedMeasures.delete(code);
                card.classList.remove('selected');
            }}
            
            updateContinueButton();
        }}
        
        function updateContinueButton() {{
            const btn = document.getElementById('continueBtn');
            const hasPas = document.getElementById('pasFile').files.length > 0;
            const hasElmhurst = document.getElementById('elmhurstFile').files.length > 0;
            const hasMeasures = selectedMeasures.size > 0;
            
            btn.disabled = !(hasPas && hasElmhurst && hasMeasures);
        }}
        
        // File upload handlers
        function setupUpload(boxId, inputId, statusId) {{
            const box = document.getElementById(boxId);
            const input = document.getElementById(inputId);
            const status = document.getElementById(statusId);
            
            box.onclick = () => input.click();
            
            ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(event => {{
                box.addEventListener(event, e => {{
                    e.preventDefault();
                    e.stopPropagation();
                }});
            }});
            
            ['dragenter', 'dragover'].forEach(event => {{
                box.addEventListener(event, () => box.classList.add('drag-over'));
            }});
            
            ['dragleave', 'drop'].forEach(event => {{
                box.addEventListener(event, () => box.classList.remove('drag-over'));
            }});
            
            box.addEventListener('drop', e => {{
                const files = e.dataTransfer.files;
                if (files.length > 0) {{
                    input.files = files;
                    handleFileSelect(input, status);
                }}
            }});
            
            input.onchange = () => handleFileSelect(input, status);
        }}
        
        function handleFileSelect(input, status) {{
            if (input.files.length > 0) {{
                const file = input.files[0];
                status.style.display = 'block';
                status.className = 'file-status success';
                status.textContent = `✓ ${{file.name}} uploaded`;
                updateContinueButton();
            }}
        }}
        
        setupUpload('pasUploadBox', 'pasFile', 'pasStatus');
        setupUpload('elmhurstUploadBox', 'elmhurstFile', 'elmhurstStatus');
        
        // Continue button - submit form
        document.getElementById('continueBtn').onclick = async () => {{
            const formData = new FormData(document.getElementById('retrofitForm'));
            
            // Add selected measures as JSON
            formData.append('selected_measures', JSON.stringify(Array.from(selectedMeasures)));
            
            // Show loading
            const btn = document.getElementById('continueBtn');
            btn.textContent = 'Processing...';
            btn.disabled = true;
            
            try {{
                const response = await fetch('/api/retrofit-process', {{
                    method: 'POST',
                    body: formData
                }});
                
                if (response.ok) {{
                    // Go to questions page
                    window.location.href = '/tool/retrofit/questions';
                }} else {{
                    alert('Error processing files. Please try again.');
                    btn.textContent = 'Continue to Questions →';
                    btn.disabled = false;
                }}
            }} catch (error) {{
                alert('Error: ' + error.message);
                btn.textContent = 'Continue to Questions →';
                btn.disabled = false;
            }}
        }};
    </script>
</body>
</html>
    """
    
    return HTMLResponse(html)


async def post_retrofit_complete(request: Request):
    """Complete workflow - generate final PDF"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row

    # Check credits
    try:
        credits = float(user_row.get("credits", 0.0))
    except Exception:
        credits = 0.0

    if credits < RETROFIT_TOOL_COST:
        return HTMLResponse(f"<h1>Insufficient Credits</h1><p>Need £{RETROFIT_TOOL_COST}</p><a href='/billing'>Top Up</a>")

    # Get form data
    form = await request.form()
    
    # Build design document
    design_doc = {
        "metadata": {
            "generated_date": datetime.now().isoformat(),
            "format": form.get("format_type", "PAS Hub")
        },
        "property": json.loads(form.get("extracted_data", "{}")),
        "calculations": json.loads(form.get("calc_data", "{}")),
        "measures": []
    }
    
    measures = json.loads(form.get("measures", "[]"))
    for code in measures:
        measure_data = {
            "code": code,
            "name": MEASURES[code]['name'],
            "answers": []
        }
        for question in MEASURES[code]['questions']:
            answer_key = f"{code}_{question['id']}"
            answer = form.get(answer_key, "")
            measure_data['answers'].append({
                "question": question['label'],
                "answer": str(answer),
                "unit": question.get('unit', '')
            })
        design_doc['measures'].append(measure_data)
    
    # Generate PDF
    try:
        pdf_bytes = generate_pdf_design(design_doc)
        
        # Deduct credits
        user_id = user_row["id"]
        new_balance = credits - RETROFIT_TOOL_COST
        update_user_credits(user_id, new_balance)
        add_transaction(user_id, -RETROFIT_TOOL_COST, "retrofit_design")
        
        # Return PDF
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=retrofit_design_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            }
        )
    except Exception as e:
        return HTMLResponse(f"<h1>Error</h1><p>{str(e)}</p><a href='/tool/retrofit'>Try Again</a>")
