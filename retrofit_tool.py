"""
Retrofit Design Tool - PHASES 1-3 CLEAN VERSION
Phase 1: Upload (Site Notes + Condition Report + Measure Sheet)
Phase 2: Calc Upload (Solar PV, Heat Pump, ESH)
Phase 3: Questions (3-tier auto-population: Site Notes > Calcs > Measure Sheet)
"""

import io
import re
import json
from datetime import datetime
from typing import Dict, List, Optional
import PyPDF2
from fastapi import UploadFile
from openpyxl import load_workbook

# =============================================================================
# MEASURE DEFINITIONS
# =============================================================================

MEASURES = {
    "loft_insulation": {
        "name": "Loft Insulation",
        "icon": "🏠",
        "category": "Insulation"
    },
    "room_in_roof": {
        "name": "Room in Roof Insulation",
        "icon": "🏠",
        "category": "Insulation"
    },
    "flat_roof_insulation": {
        "name": "Flat Roof Insulation",
        "icon": "🏠",
        "category": "Insulation"
    },
    "cavity_wall_insulation": {
        "name": "Cavity Wall Insulation",
        "icon": "🧱",
        "category": "Insulation"
    },
    "solid_wall_insulation_internal": {
        "name": "Solid Wall Insulation (Internal)",
        "icon": "🧱",
        "category": "Insulation"
    },
    "solid_wall_insulation_external": {
        "name": "Solid Wall Insulation (External)",
        "icon": "🧱",
        "category": "Insulation"
    },
    "park_home_insulation": {
        "name": "Park Home Insulation",
        "icon": "🏠",
        "category": "Insulation"
    },
    "underfloor_insulation": {
        "name": "Underfloor Insulation",
        "icon": "🏗️",
        "category": "Insulation"
    },
    "solar_pv": {
        "name": "Solar PV",
        "icon": "☀️",
        "category": "Renewable Energy"
    },
    "air_source_heat_pump": {
        "name": "Air Source Heat Pump",
        "icon": "♨️",
        "category": "Heating"
    },
    "ground_source_heat_pump": {
        "name": "Ground Source Heat Pump",
        "icon": "♨️",
        "category": "Heating"
    },
    "hybrid_heat_pump": {
        "name": "Hybrid Heat Pump",
        "icon": "♨️",
        "category": "Heating"
    },
    "first_time_central_heating": {
        "name": "First Time Central Heating",
        "icon": "🔥",
        "category": "Heating"
    },
    "electric_storage_heaters": {
        "name": "Electric Storage Heaters",
        "icon": "🔌",
        "category": "Heating"
    },
    "secondary_heating": {
        "name": "Secondary Heating",
        "icon": "🔥",
        "category": "Heating"
    },
    "hot_water_cylinder": {
        "name": "Hot Water Cylinder",
        "icon": "💧",
        "category": "Hot Water"
    },
    "cylinder_thermostat": {
        "name": "Cylinder Thermostat",
        "icon": "🌡️",
        "category": "Controls"
    },
    "heating_controls_upgrade": {
        "name": "Heating Controls Upgrade",
        "icon": "🎚️",
        "category": "Controls"
    },
    "smart_heating_controls": {
        "name": "Smart Heating Controls",
        "icon": "📱",
        "category": "Controls"
    },
    "double_glazing": {
        "name": "Double Glazing",
        "icon": "🪟",
        "category": "Windows & Doors"
    },
    "secondary_glazing": {
        "name": "Secondary Glazing",
        "icon": "🪟",
        "category": "Windows & Doors"
    },
    "door_upgrade": {
        "name": "Door Upgrade",
        "icon": "🚪",
        "category": "Windows & Doors"
    },
    "draught_proofing": {
        "name": "Draught Proofing",
        "icon": "💨",
        "category": "Windows & Doors"
    }
}

# =============================================================================
# QUESTION DEFINITIONS WITH FIELD MAPPING
# =============================================================================

MEASURE_QUESTIONS = {
    "loft_insulation": [
        {
            "id": "loft_current_depth",
            "question": "What is the current loft insulation depth?",
            "type": "number",
            "unit": "mm",
            "site_notes_fields": ["loft_insulation_depth", "current_loft_depth"],
            "measure_sheet_field": "Current Loft Insulation Depth (mm)",
            "calc_pdf_fields": []
        },
        {
            "id": "loft_new_depth",
            "question": "What depth of loft insulation will be installed?",
            "type": "number",
            "unit": "mm",
            "default": 300,
            "site_notes_fields": ["new_loft_depth", "proposed_loft_depth"],
            "measure_sheet_field": "New Loft Insulation Depth (mm)",
            "calc_pdf_fields": []
        },
        {
            "id": "loft_area",
            "question": "What is the total loft area?",
            "type": "number",
            "unit": "m²",
            "site_notes_fields": ["loft_area", "total_loft_area"],
            "measure_sheet_field": "Loft Area (m²)",
            "calc_pdf_fields": []
        }
    ],
    "solar_pv": [
        {
            "id": "solar_system_size",
            "question": "What is the system size?",
            "type": "number",
            "unit": "kWp",
            "site_notes_fields": ["solar_system_size", "pv_system_size"],
            "measure_sheet_field": "Solar PV System Size (kWp)",
            "calc_pdf_fields": ["system_size", "installed_capacity", "total_kwp"]
        },
        {
            "id": "solar_panel_count",
            "question": "How many panels will be installed?",
            "type": "number",
            "unit": "panels",
            "site_notes_fields": ["number_of_panels", "panel_count"],
            "measure_sheet_field": "Number of Solar Panels",
            "calc_pdf_fields": ["number_of_panels", "panel_count", "total_panels"]
        },
        {
            "id": "solar_annual_generation",
            "question": "What is the estimated annual generation?",
            "type": "number",
            "unit": "kWh",
            "site_notes_fields": ["annual_generation", "yearly_generation"],
            "measure_sheet_field": "Annual Generation (kWh)",
            "calc_pdf_fields": ["annual_generation", "yearly_output", "estimated_generation"]
        }
    ],
    "air_source_heat_pump": [
        {
            "id": "hp_capacity",
            "question": "What is the heat pump capacity?",
            "type": "number",
            "unit": "kW",
            "site_notes_fields": ["heat_pump_capacity", "hp_output"],
            "measure_sheet_field": "Heat Pump Capacity (kW)",
            "calc_pdf_fields": ["heat_pump_size", "output_capacity", "hp_capacity"]
        },
        {
            "id": "hp_scop",
            "question": "What is the SCOP (Seasonal Coefficient of Performance)?",
            "type": "number",
            "unit": "",
            "site_notes_fields": ["scop", "seasonal_cop"],
            "measure_sheet_field": "SCOP",
            "calc_pdf_fields": ["scop", "seasonal_cop", "efficiency"]
        }
    ],
    "electric_storage_heaters": [
        {
            "id": "esh_number",
            "question": "How many storage heaters will be installed?",
            "type": "number",
            "unit": "heaters",
            "site_notes_fields": ["number_of_heaters", "heater_count"],
            "measure_sheet_field": "Number of Storage Heaters",
            "calc_pdf_fields": ["number_of_heaters", "heater_count", "total_heaters"]
        },
        {
            "id": "esh_total_capacity",
            "question": "What is the total heating capacity?",
            "type": "number",
            "unit": "kW",
            "site_notes_fields": ["total_heating_capacity", "esh_capacity"],
            "measure_sheet_field": "Total Heating Capacity (kW)",
            "calc_pdf_fields": ["total_capacity", "heating_output", "total_kw"]
        }
    ],
    "cavity_wall_insulation": [
        {
            "id": "cwi_area",
            "question": "What is the total wall area to be insulated?",
            "type": "number",
            "unit": "m²",
            "site_notes_fields": ["cavity_wall_area", "cwi_area"],
            "measure_sheet_field": "Cavity Wall Area (m²)",
            "calc_pdf_fields": []
        }
    ]
}

# =============================================================================
# PDF EXTRACTION FUNCTIONS
# =============================================================================

def extract_text_from_pdf(pdf_file: UploadFile) -> str:
    """Extract text from PDF file."""
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_file.file.read()))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        return text
    except Exception as e:
        return f"Error extracting PDF: {str(e)}"

def extract_data_from_site_notes(pdf_text: str) -> Dict:
    """Extract data from Site Notes PDF with improved pattern matching."""
    data = {}
    
    patterns = {
        "address": r"(?:Property Address|Address)[:\s]+([^\n]+)",
        "postcode": r"([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})",
        "uprn": r"(?:UPRN|uprn)[:\s]+(\d+)",
        "property_type": r"(?:Property Type|Type)[:\s]+([^\n]+)",
        "construction_age": r"(?:Construction Age|Age Band|Built)[:\s]+([^\n]+)",
        "wall_type": r"(?:Wall Construction|Wall Type)[:\s]+([^\n]+)",
        "floor_area": r"(?:Total Floor Area|Floor Area)[:\s]+(\d+(?:\.\d+)?)\s*m",
        "loft_area": r"(?:Loft Area|Roof Space)[:\s]+(\d+(?:\.\d+)?)\s*m",
        "loft_insulation_depth": r"(?:Loft Insulation|Current Loft)[:\s]+(\d+)\s*mm",
        "epc_rating": r"(?:EPC Rating|Current Rating)[:\s]+([A-G])",
        "solar_system_size": r"(?:Solar PV|System Size)[:\s]+(\d+(?:\.\d+)?)\s*kWp",
        "number_of_panels": r"(?:Number of Panels|Panel Count)[:\s]+(\d+)",
        "heat_pump_capacity": r"(?:Heat Pump|ASHP|Capacity)[:\s]+(\d+(?:\.\d+)?)\s*kW"
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, pdf_text, re.IGNORECASE)
        if match:
            data[key] = match.group(1).strip()
    
    return data

def extract_data_from_calc_pdf(pdf_text: str, calc_type: str) -> Dict:
    """Extract calculation data from uploaded calc PDFs."""
    data = {}
    
    if calc_type == "solar_pv":
        patterns = {
            "system_size": r"(?:System Size|Capacity|Total kWp)[:\s]+(\d+(?:\.\d+)?)",
            "number_of_panels": r"(?:Number of Panels|Panel Count)[:\s]+(\d+)",
            "annual_generation": r"(?:Annual Generation|Yearly Output|Est\. Generation)[:\s]+(\d+(?:,\d+)?)"
        }
    elif calc_type == "heat_pump":
        patterns = {
            "heat_pump_size": r"(?:Heat Pump Size|Capacity|Output)[:\s]+(\d+(?:\.\d+)?)\s*kW",
            "scop": r"(?:SCOP|Seasonal COP|Efficiency)[:\s]+(\d+(?:\.\d+)?)"
        }
    elif calc_type == "esh":
        patterns = {
            "number_of_heaters": r"(?:Number of Heaters|Heater Count|Total Units)[:\s]+(\d+)",
            "total_capacity": r"(?:Total Capacity|Heating Output|Total kW)[:\s]+(\d+(?:\.\d+)?)"
        }
    else:
        return data
    
    for key, pattern in patterns.items():
        match = re.search(pattern, pdf_text, re.IGNORECASE)
        if match:
            value = match.group(1).strip().replace(',', '')
            data[key] = value
    
    return data

def extract_data_from_measure_sheet(file: UploadFile) -> Dict:
    """Extract data from Measure Info Sheet Excel file."""
    try:
        wb = load_workbook(filename=io.BytesIO(file.file.read()))
        ws = wb.active
        
        data = {}
        
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[0] and row[1]:
                field_name = str(row[0]).strip()
                field_value = str(row[1]).strip()
                data[field_name] = field_value
        
        return data
    except Exception as e:
        return {"error": f"Error reading measure sheet: {str(e)}"}

# =============================================================================
# AUTO-POPULATION LOGIC
# =============================================================================

def get_field_value_with_source(question: Dict, site_notes_data: Dict, calc_data: Dict, measure_sheet_data: Dict) -> tuple:
    """
    Get field value with 3-tier priority and return (value, source)
    Priority: 1) Site Notes, 2) Calc PDFs, 3) Measure Sheet
    """
    # Priority 1: Site Notes
    for field in question.get("site_notes_fields", []):
        if field in site_notes_data and site_notes_data[field]:
            return site_notes_data[field], "site_notes"
    
    # Priority 2: Calc PDFs
    for field in question.get("calc_pdf_fields", []):
        if field in calc_data and calc_data[field]:
            return calc_data[field], "calc_pdf"
    
    # Priority 3: Measure Sheet
    measure_field = question.get("measure_sheet_field")
    if measure_field and measure_field in measure_sheet_data and measure_sheet_data[measure_field]:
        return measure_sheet_data[measure_field], "measure_sheet"
    
    # No data found
    return question.get("default", ""), "none"

# =============================================================================
# HTML PAGES
# =============================================================================

def get_retrofit_tool_page():
    """Phase 1: Upload page with format selection and file uploads."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Retrofit Design Tool - Upload</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }}
            
            .container {{
                max-width: 800px;
                margin: 0 auto;
            }}
            
            .header {{
                text-align: center;
                color: white;
                margin-bottom: 30px;
            }}
            
            .header h1 {{
                font-size: 32px;
                font-weight: 700;
                margin-bottom: 10px;
            }}
            
            .header p {{
                font-size: 16px;
                opacity: 0.9;
            }}
            
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
                color: #1a1a1a;
                margin-bottom: 20px;
                display: flex;
                align-items: center;
                gap: 10px;
            }}
            
            .format-selector {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
                margin-bottom: 20px;
            }}
            
            .format-card {{
                border: 3px solid #e0e0e0;
                border-radius: 12px;
                padding: 30px 20px;
                cursor: pointer;
                transition: all 0.3s ease;
                text-align: center;
                background: white;
            }}
            
            .format-card:hover {{
                border-color: #667eea;
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.2);
            }}
            
            .format-card.selected {{
                border-color: #667eea;
                background: linear-gradient(135deg, #f0f4ff 0%, #e0e7ff 100%);
                box-shadow: 0 4px 20px rgba(102, 126, 234, 0.3);
            }}
            
            .format-icon {{
                font-size: 48px;
                margin-bottom: 12px;
            }}
            
            .format-name {{
                font-weight: 700;
                font-size: 18px;
                color: #1a1a1a;
                margin-bottom: 8px;
            }}
            
            .format-desc {{
                font-size: 14px;
                color: #666;
            }}
            
            .upload-section {{
                margin-bottom: 24px;
            }}
            
            .upload-label {{
                display: flex;
                align-items: center;
                gap: 8px;
                font-weight: 600;
                font-size: 15px;
                color: #2d3748;
                margin-bottom: 10px;
            }}
            
            .required {{
                color: #e53e3e;
                font-weight: 700;
            }}
            
            .optional {{
                color: #f59e0b;
                font-size: 13px;
                font-weight: 600;
                background: #fef3c7;
                padding: 2px 8px;
                border-radius: 4px;
            }}
            
            .upload-box {{
                border: 2px dashed #cbd5e0;
                border-radius: 12px;
                padding: 24px;
                text-align: center;
                cursor: pointer;
                transition: all 0.3s ease;
                background: #f7fafc;
            }}
            
            .upload-box:hover {{
                border-color: #667eea;
                background: #f0f4ff;
            }}
            
            .upload-box.has-file {{
                border-color: #48bb78;
                background: #f0fff4;
            }}
            
            .upload-icon {{
                font-size: 40px;
                margin-bottom: 12px;
            }}
            
            .upload-text {{
                font-size: 14px;
                color: #4a5568;
                margin-bottom: 8px;
            }}
            
            .file-name {{
                font-weight: 600;
                color: #2d3748;
                margin-top: 8px;
            }}
            
            .btn {{
                width: 100%;
                padding: 16px;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s ease;
                margin-top: 10px;
            }}
            
            .btn-primary {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }}
            
            .btn-primary:hover {{
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
            }}
            
            .btn-primary:disabled {{
                opacity: 0.5;
                cursor: not-allowed;
                transform: none;
            }}
            
            input[type="file"] {{
                display: none;
            }}
            
            .info-banner {{
                background: #eef2ff;
                border-left: 4px solid #667eea;
                padding: 16px;
                border-radius: 8px;
                margin-bottom: 20px;
            }}
            
            .info-banner p {{
                color: #4c51bf;
                font-size: 14px;
                line-height: 1.5;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🏠 Retrofit Design Tool</h1>
                <p>Upload your documents to generate professional retrofit designs</p>
            </div>
            
            <form id="uploadForm" action="/calc-upload" method="post" enctype="multipart/form-data">
                <div class="card">
                    <div class="section-title">
                        📋 Select Output Format
                    </div>
                    
                    <div class="format-selector">
                        <div class="format-card" onclick="selectFormat('elmhurst')">
                            <div class="format-icon">🏛️</div>
                            <div class="format-name">Elmhurst Style</div>
                            <div class="format-desc">Traditional format cards</div>
                        </div>
                        <div class="format-card" onclick="selectFormat('pas_hub')">
                            <div class="format-icon">⚡</div>
                            <div class="format-name">PAS Hub Style</div>
                            <div class="format-desc">Modern format cards</div>
                        </div>
                    </div>
                    
                    <input type="hidden" name="format_style" id="formatStyle" value="">
                </div>
                
                <div class="card">
                    <div class="info-banner">
                        <p><strong>📊 Data Priority:</strong> 🔵 Site Notes → 🟢 Calc PDFs → 🟡 Measure Sheet (fallback)</p>
                    </div>
                    
                    <div class="section-title">
                        📄 Required Documents
                    </div>
                    
                    <div class="upload-section">
                        <div class="upload-label">
                            Site Notes PDF <span class="required">*</span>
                        </div>
                        <div class="upload-box" id="siteNotesBox" onclick="document.getElementById('siteNotes').click()">
                            <div class="upload-icon">📄</div>
                            <div class="upload-text">Click to upload Site Notes PDF</div>
                            <div class="file-name" id="siteNotesName"></div>
                        </div>
                        <input type="file" id="siteNotes" name="site_notes" accept=".pdf" required>
                    </div>
                    
                    <div class="upload-section">
                        <div class="upload-label">
                            Condition Report PDF <span class="required">*</span>
                        </div>
                        <div class="upload-box" id="conditionBox" onclick="document.getElementById('conditionReport').click()">
                            <div class="upload-icon">📄</div>
                            <div class="upload-text">Click to upload Condition Report PDF</div>
                            <div class="file-name" id="conditionName"></div>
                        </div>
                        <input type="file" id="conditionReport" name="condition_report" accept=".pdf" required>
                    </div>
                </div>
                
                <div class="card">
                    <div class="section-title">
                        📊 Optional - Fallback Data Source
                    </div>
                    
                    <div class="upload-section">
                        <div class="upload-label">
                            Measure Info Sheet <span class="optional">OPTIONAL</span>
                        </div>
                        <div class="upload-box" id="measureBox" onclick="document.getElementById('measureSheet').click()">
                            <div class="upload-icon">📊</div>
                            <div class="upload-text">Click to upload Measure Sheet Excel (.xlsx)</div>
                            <div class="file-name" id="measureName"></div>
                        </div>
                        <input type="file" id="measureSheet" name="measure_sheet" accept=".xlsx,.xls">
                        <p style="font-size: 13px; color: #666; margin-top: 8px;">
                            🟡 Used as fallback when Site Notes or Calc PDFs don't contain specific data
                        </p>
                    </div>
                </div>
                
                <button type="submit" class="btn btn-primary" id="submitBtn" disabled>
                    Continue to Calculations →
                </button>
            </form>
        </div>
        
        <script>
            let selectedFormat = '';
            
            function selectFormat(format) {{
                selectedFormat = format;
                document.getElementById('formatStyle').value = format;
                
                document.querySelectorAll('.format-card').forEach(card => {{
                    card.classList.remove('selected');
                }});
                
                event.currentTarget.classList.add('selected');
                
                checkFormValidity();
            }}
            
            function setupFileInput(inputId, boxId, nameId) {{
                const input = document.getElementById(inputId);
                const box = document.getElementById(boxId);
                const status = document.getElementById(nameId);
                
                input.addEventListener('change', function(e) {{
                    handleFileSelect(input, status);
                }});
            }}
            
            function handleFileSelect(input, status) {{
                if (input.files && input.files[0]) {{
                    const fileName = input.files[0].name;
                    status.textContent = '✓ ' + fileName;
                    status.parentElement.classList.add('has-file');
                }} else {{
                    status.textContent = '';
                    status.parentElement.classList.remove('has-file');
                }}
                checkFormValidity();
            }}
            
            function checkFormValidity() {{
                const siteNotes = document.getElementById('siteNotes').files.length > 0;
                const conditionReport = document.getElementById('conditionReport').files.length > 0;
                const formatSelected = selectedFormat !== '';
                
                const submitBtn = document.getElementById('submitBtn');
                submitBtn.disabled = !(siteNotes && conditionReport && formatSelected);
            }}
            
            setupFileInput('siteNotes', 'siteNotesBox', 'siteNotesName');
            setupFileInput('conditionReport', 'conditionBox', 'conditionName');
            setupFileInput('measureSheet', 'measureBox', 'measureName');
        </script>
    </body>
    </html>
    """

def get_calc_upload_page(session_data: Dict):
    """Phase 2: Calculation file upload page."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Upload Calculations - Retrofit Tool</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }}
            
            .container {{
                max-width: 800px;
                margin: 0 auto;
            }}
            
            .header {{
                text-align: center;
                color: white;
                margin-bottom: 30px;
            }}
            
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
            }}
            
            .upload-section {{
                margin-bottom: 20px;
            }}
            
            .upload-label {{
                font-weight: 500;
                margin-bottom: 10px;
                display: flex;
                align-items: center;
                gap: 8px;
            }}
            
            .upload-box {{
                border: 2px dashed #cbd5e0;
                border-radius: 12px;
                padding: 24px;
                text-align: center;
                cursor: pointer;
                transition: all 0.3s ease;
                background: #f7fafc;
            }}
            
            .upload-box:hover {{
                border-color: #667eea;
                background: #f0f4ff;
            }}
            
            .upload-box.has-file {{
                border-color: #48bb78;
                background: #f0fff4;
            }}
            
            .btn {{
                width: 100%;
                padding: 16px;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s ease;
                margin-top: 10px;
            }}
            
            .btn-primary {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }}
            
            input[type="file"] {{
                display: none;
            }}
            
            .info-banner {{
                background: #eef2ff;
                border-left: 4px solid #667eea;
                padding: 16px;
                border-radius: 8px;
                margin-bottom: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📊 Upload Calculations</h1>
                <p>Upload calculation PDFs for automatic data extraction</p>
            </div>
            
            <form action="/questions" method="post" enctype="multipart/form-data">
                <div class="card">
                    <div class="info-banner">
                        <p><strong>Optional:</strong> Upload calc PDFs to auto-fill questions. Skip if not available.</p>
                    </div>
                    
                    <div class="upload-section">
                        <div class="upload-label">☀️ Solar PV Calculation</div>
                        <div class="upload-box" onclick="document.getElementById('solarCalc').click()">
                            <div>Click to upload Solar PV calc PDF</div>
                        </div>
                        <input type="file" id="solarCalc" name="solar_calc" accept=".pdf">
                    </div>
                    
                    <div class="upload-section">
                        <div class="upload-label">♨️ Heat Pump Calculation</div>
                        <div class="upload-box" onclick="document.getElementById('hpCalc').click()">
                            <div>Click to upload Heat Pump calc PDF</div>
                        </div>
                        <input type="file" id="hpCalc" name="hp_calc" accept=".pdf">
                    </div>
                    
                    <div class="upload-section">
                        <div class="upload-label">🔌 ESH Calculation</div>
                        <div class="upload-box" onclick="document.getElementById('eshCalc').click()">
                            <div>Click to upload ESH calc PDF</div>
                        </div>
                        <input type="file" id="eshCalc" name="esh_calc" accept=".pdf">
                    </div>
                </div>
                
                <button type="submit" class="btn btn-primary">
                    Continue to Questions →
                </button>
            </form>
        </div>
        
        <script>
            document.querySelectorAll('input[type="file"]').forEach(input => {{
                input.addEventListener('change', function() {{
                    if (this.files[0]) {{
                        this.parentElement.querySelector('.upload-box').classList.add('has-file');
                        this.parentElement.querySelector('.upload-box div').textContent = '✓ ' + this.files[0].name;
                    }}
                }});
            }});
        </script>
    </body>
    </html>
    """

def get_retrofit_questions_page(session_data: Dict):
    """Phase 3: Questions page with 3-tier auto-population."""
    site_notes_data = session_data.get('site_notes_data', {})
    calc_data = session_data.get('calc_data', {})
    measure_sheet_data = session_data.get('measure_sheet_data', {})
    
    questions_html = ""
    
    for measure_id in session_data.get('selected_measures', []):
        if measure_id not in MEASURE_QUESTIONS:
            continue
        
        measure_info = MEASURES.get(measure_id, {})
        questions = MEASURE_QUESTIONS[measure_id]
        
        questions_html += f"""
        <div class="measure-section">
            <div class="measure-header">
                <span class="measure-icon">{measure_info.get('icon', '📋')}</span>
                <span class="measure-name">{measure_info.get('name', measure_id)}</span>
            </div>
            <div class="questions-grid">
        """
        
        for question in questions:
            value, source = get_field_value_with_source(
                question, site_notes_data, calc_data, measure_sheet_data
            )
            
            source_badge = ""
            if source == "site_notes":
                source_badge = '<span class="badge badge-site">🔵 Site Notes</span>'
            elif source == "calc_pdf":
                source_badge = '<span class="badge badge-calc">🟢 Calc PDF</span>'
            elif source == "measure_sheet":
                source_badge = '<span class="badge badge-measure">🟡 Measure Sheet</span>'
            
            questions_html += f"""
            <div class="question-item">
                <label>{question['question']}</label>
                {source_badge}
                <div class="input-group">
                    <input type="{question['type']}" 
                           name="{measure_id}_{question['id']}" 
                           value="{value}"
                           placeholder="Enter value">
                    {f'<span class="unit">{question["unit"]}</span>' if question.get('unit') else ''}
                </div>
            </div>
            """
        
        questions_html += """
            </div>
        </div>
        """
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Measure Questions - Retrofit Tool</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }}
            
            .container {{
                max-width: 1000px;
                margin: 0 auto;
            }}
            
            .header {{
                text-align: center;
                color: white;
                margin-bottom: 30px;
            }}
            
            .measure-section {{
                background: white;
                border-radius: 16px;
                padding: 30px;
                margin-bottom: 20px;
            }}
            
            .measure-header {{
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 20px;
                font-size: 20px;
                font-weight: 600;
            }}
            
            .questions-grid {{
                display: grid;
                gap: 20px;
            }}
            
            .question-item {{
                display: flex;
                flex-direction: column;
                gap: 8px;
            }}
            
            .question-item label {{
                font-weight: 500;
                color: #333;
            }}
            
            .input-group {{
                display: flex;
                align-items: center;
                gap: 8px;
            }}
            
            .input-group input {{
                flex: 1;
                padding: 12px;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                font-size: 14px;
            }}
            
            .unit {{
                color: #666;
                font-size: 14px;
                min-width: 40px;
            }}
            
            .badge {{
                display: inline-block;
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 600;
            }}
            
            .badge-site {{
                background: #dbeafe;
                color: #1e40af;
            }}
            
            .badge-calc {{
                background: #d1fae5;
                color: #065f46;
            }}
            
            .badge-measure {{
                background: #fef3c7;
                color: #92400e;
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
                margin-top: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📋 Measure Questions</h1>
                <p>Review and complete the auto-filled data</p>
            </div>
            
            <form action="/review" method="post">
                {questions_html}
                
                <button type="submit" class="btn">
                    Continue to Review →
                </button>
            </form>
        </div>
    </body>
    </html>
    """
