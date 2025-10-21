"""
Retrofit Design Tool - COMPLETE WITH MEASURE SHEET FALLBACK
Priority: Site Notes > Calc PDFs > Measure Sheet
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

from auth import require_active_user_row
from database import update_user_credits, add_transaction

RETROFIT_TOOL_COST = 10.0

# ==================== MEASURES CONFIGURATION ====================

MEASURES = {
    "LOFT": {
        "name": "Loft Insulation",
        "code": "LOFT",
        "icon": "🏠",
        "requires_calc": False,
        "questions": [
            {"id": "area", "label": "M2 Area being treated", "type": "number", "unit": "m²", "auto_populate": True, "measure_sheet_key": "area"},
            {"id": "existing", "label": "Existing Loft insulation Thickness", "type": "text", "auto_populate": True, "measure_sheet_key": "existing"}
        ]
    },
    "ESH": {
        "name": "Electric Storage Heater",
        "code": "ESH",
        "icon": "🔌",
        "requires_calc": True,
        "questions": [
            {"id": "manufacturer", "label": "Manufacturer", "type": "text", "auto_populate": True, "calc_key": "manufacturer", "measure_sheet_key": "manufacturer"},
            {"id": "calc", "label": "Heat Demand Calculator included Y/N?", "type": "yesno", "auto_populate": False, "measure_sheet_key": "calc"},
            {"id": "model", "label": "Model numbers", "type": "text", "auto_populate": True, "calc_key": "models", "measure_sheet_key": "model"}
        ]
    },
    "PRT": {
        "name": "Programmable Room Thermostat",
        "code": "PRT",
        "icon": "🌡️",
        "requires_calc": False,
        "questions": [
            {"id": "model", "label": "Make and model being installed", "type": "text", "auto_populate": False, "measure_sheet_key": "model"}
        ]
    },
    "TRV": {
        "name": "Thermostatic Radiator Valves",
        "code": "TRV",
        "icon": "🎚️",
        "requires_calc": False,
        "questions": [
            {"id": "model", "label": "Make and model being installed", "type": "text", "auto_populate": False, "measure_sheet_key": "model"},
            {"id": "quantity", "label": "Number of TRV's being installed", "type": "number", "auto_populate": True, "measure_sheet_key": "quantity"}
        ]
    },
    "GAS_BOILER": {
        "name": "Gas Boiler Replacement",
        "code": "GAS_BOILER",
        "icon": "🔥",
        "requires_calc": True,
        "questions": [
            {"id": "model", "label": "Make and model being installed", "type": "text", "auto_populate": False, "measure_sheet_key": "model"},
            {"id": "size", "label": "Boiler KW size req", "type": "number", "unit": "KW", "auto_populate": False, "measure_sheet_key": "size"},
            {"id": "calc", "label": "Heat Demand Calculator included Y/N?", "type": "yesno", "auto_populate": False, "measure_sheet_key": "calc"}
        ]
    },
    "HEAT_PUMP": {
        "name": "Heat Pump",
        "code": "HEAT_PUMP",
        "icon": "♨️",
        "requires_calc": True,
        "questions": [
            {"id": "model", "label": "Make and model being installed", "type": "text", "auto_populate": True, "calc_key": "model", "measure_sheet_key": "model"},
            {"id": "size", "label": "Heat pump size req (KW)", "type": "number", "unit": "KW", "auto_populate": True, "calc_key": "heatPumpSizeNumeric", "measure_sheet_key": "size"},
            {"id": "calc", "label": "Heat Demand Calculator included Y/N?", "type": "yesno", "auto_populate": False, "measure_sheet_key": "calc"}
        ]
    },
    "SOLAR_PV": {
        "name": "Solar PV",
        "code": "SOLAR_PV",
        "icon": "☀️",
        "requires_calc": True,
        "questions": [
            {"id": "model", "label": "Make and model being installed", "type": "text", "auto_populate": True, "calc_key": "model", "measure_sheet_key": "model"},
            {"id": "size", "label": "System size (KW)", "type": "number", "unit": "KW", "auto_populate": True, "calc_key": "systemSizeNumeric", "measure_sheet_key": "size"},
            {"id": "calc", "label": "Solar PV Calculations included?", "type": "yesno", "auto_populate": False, "measure_sheet_key": "calc"}
        ]
    },
    "IWI": {
        "name": "Internal Wall Insulation",
        "code": "IWI",
        "icon": "🗂️",
        "requires_calc": False,
        "questions": [
            {"id": "area", "label": "M2 Area being treated", "type": "number", "unit": "m²", "auto_populate": True, "measure_sheet_key": "area"},
            {"id": "omitted", "label": "Rooms being omitted from Install?", "type": "text", "auto_populate": False, "measure_sheet_key": "omitted"}
        ]
    },
    "CWI": {
        "name": "Cavity Wall Insulation",
        "code": "CWI",
        "icon": "🧱",
        "requires_calc": False,
        "questions": [
            {"id": "area", "label": "M2 Area being treated", "type": "number", "unit": "m²", "auto_populate": True, "measure_sheet_key": "area"},
            {"id": "width", "label": "Cavity width", "type": "text", "auto_populate": True, "measure_sheet_key": "width"},
            {"id": "product", "label": "CWI Product being used", "type": "text", "auto_populate": False, "measure_sheet_key": "product"}
        ]
    },
    "RIR": {
        "name": "Room in Roof",
        "code": "RIR",
        "icon": "🏠",
        "requires_calc": False,
        "questions": [
            {"id": "area", "label": "M2 Area being treated", "type": "number", "unit": "m²", "auto_populate": True, "measure_sheet_key": "area"}
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


def parse_measure_sheet(sheet_text: str) -> Dict:
    """Parse Measure Design Data Collection Sheet - FALLBACK SOURCE"""
    data = {}
    
    measure_sections = {
        "LOFT": ["M2 Area being treated", "Existing Loft insulation Thickness"],
        "ESH": ["Manufacturer", "Heat Demand Calculator included", "Model numbers"],
        "PRT": ["Make and model being installed"],
        "TRV": ["Make and model being installed", "Number of TRV"],
        "GAS_BOILER": ["Make and model being installed", "Boiler KW size req", "Heat Demand Calculator included"],
        "HEAT_PUMP": ["Make and model being installed", "Heat pump size req", "Heat Demand Calculator included"],
        "SOLAR_PV": ["Make and model being installed", "System size", "Solar PV Calculations included"],
        "IWI": ["M2 Area being treated", "Rooms being omitted"],
        "CWI": ["M2 Area being treated", "Cavity width", "CWI Product being used"],
        "RIR": ["M2 Area being treated"]
    }
    
    for measure_code, fields in measure_sections.items():
        data[measure_code] = {}
        
        measure_match = re.search(rf'{measure_code}\s+(.*?)(?=\n[A-Z]{{2,}}|\Z)', sheet_text, re.DOTALL | re.IGNORECASE)
        if not measure_match:
            continue
            
        section_text = measure_match.group(1)
        
        if measure_code == "LOFT":
            area_match = re.search(r'M2 Area being treated\s+([0-9.]+)', section_text, re.IGNORECASE)
            if area_match:
                data[measure_code]['area'] = area_match.group(1)
            
            existing_match = re.search(r'Existing Loft insulation Thickness\s+([0-9]+)', section_text, re.IGNORECASE)
            if existing_match:
                data[measure_code]['existing'] = f"{existing_match.group(1)}mm"
        
        elif measure_code == "ESH":
            mfr_match = re.search(r'Manufacturer\s+([^\n]+)', section_text, re.IGNORECASE)
            if mfr_match and mfr_match.group(1).strip():
                data[measure_code]['manufacturer'] = mfr_match.group(1).strip()
            
            calc_match = re.search(r'Heat Demand Calculator included Y/N\?\s+([YN])', section_text, re.IGNORECASE)
            if calc_match:
                data[measure_code]['calc'] = 'Yes' if calc_match.group(1).upper() == 'Y' else 'No'
            
            model_match = re.search(r'Model numbers\s+([^\n]+)', section_text, re.IGNORECASE)
            if model_match and model_match.group(1).strip():
                data[measure_code]['model'] = model_match.group(1).strip()
        
        elif measure_code == "PRT":
            model_match = re.search(r'Make and model being installed\s+([^\n]+)', section_text, re.IGNORECASE)
            if model_match and model_match.group(1).strip():
                data[measure_code]['model'] = model_match.group(1).strip()
        
        elif measure_code == "TRV":
            model_match = re.search(r'Make and model being installed\s+([^\n]+)', section_text, re.IGNORECASE)
            if model_match and model_match.group(1).strip():
                data[measure_code]['model'] = model_match.group(1).strip()
            
            qty_match = re.search(r'Number of TRV.*?([0-9]+)', section_text, re.IGNORECASE)
            if qty_match:
                data[measure_code]['quantity'] = qty_match.group(1)
        
        elif measure_code == "GAS_BOILER":
            model_match = re.search(r'Make and model being installed\s+([^\n]+)', section_text, re.IGNORECASE)
            if model_match and model_match.group(1).strip():
                data[measure_code]['model'] = model_match.group(1).strip()
            
            size_match = re.search(r'Boiler KW size req\s+([0-9.]+)', section_text, re.IGNORECASE)
            if size_match:
                data[measure_code]['size'] = size_match.group(1)
            
            calc_match = re.search(r'Heat Demand Calculator included Y/N\?\s+([YN])', section_text, re.IGNORECASE)
            if calc_match:
                data[measure_code]['calc'] = 'Yes' if calc_match.group(1).upper() == 'Y' else 'No'
        
        elif measure_code == "HEAT_PUMP":
            model_match = re.search(r'Make and model being installed\s+([^\n]+?)(?=\s*\n|Heat pump)', section_text, re.IGNORECASE)
            if model_match and model_match.group(1).strip():
                data[measure_code]['model'] = model_match.group(1).strip()
            
            size_match = re.search(r'Heat pump size req.*?([0-9.]+)', section_text, re.IGNORECASE)
            if size_match:
                data[measure_code]['size'] = size_match.group(1)
            
            calc_match = re.search(r'Heat Demand Calculator included Y/N\?\s+([YN])', section_text, re.IGNORECASE)
            if calc_match:
                data[measure_code]['calc'] = 'Yes' if calc_match.group(1).upper() == 'Y' else 'No'
        
        elif measure_code == "SOLAR_PV":
            model_match = re.search(r'Make and model being installed\s+([^\n]+?)(?=\s*\n|System size)', section_text, re.IGNORECASE)
            if model_match and model_match.group(1).strip():
                data[measure_code]['model'] = model_match.group(1).strip()
            
            size_match = re.search(r'System size.*?([0-9.]+)', section_text, re.IGNORECASE)
            if size_match:
                data[measure_code]['size'] = size_match.group(1)
            
            calc_match = re.search(r'Solar PV Calculations included\?\s+([YN])', section_text, re.IGNORECASE)
            if calc_match:
                data[measure_code]['calc'] = 'Yes' if calc_match.group(1).upper() == 'Y' else 'No'
        
        elif measure_code in ["IWI", "RIR"]:
            area_match = re.search(r'M2 Area being treated\s+([0-9.]+)', section_text, re.IGNORECASE)
            if area_match:
                data[measure_code]['area'] = area_match.group(1)
            
            if measure_code == "IWI":
                omitted_match = re.search(r'Rooms being omitted from Install\?\s+([^\n]+)', section_text, re.IGNORECASE)
                if omitted_match and omitted_match.group(1).strip():
                    data[measure_code]['omitted'] = omitted_match.group(1).strip()
        
        elif measure_code == "CWI":
            area_match = re.search(r'M2 Area being treated\s+([0-9.]+)', section_text, re.IGNORECASE)
            if area_match:
                data[measure_code]['area'] = area_match.group(1)
            
            width_match = re.search(r'Cavity width\s+([^\n]+)', section_text, re.IGNORECASE)
            if width_match and width_match.group(1).strip():
                data[measure_code]['width'] = width_match.group(1).strip()
            
            product_match = re.search(r'CWI Product being used\s+([^\n]+)', section_text, re.IGNORECASE)
            if product_match and product_match.group(1).strip():
                data[measure_code]['product'] = product_match.group(1).strip()
    
    return data


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
    
    age_range_match = re.search(r'(?:Age Range|Built)[:\s]+(19\d{2}|20\d{2})\s*-\s*(19\d{2}|20\d{2})', combined_text, re.IGNORECASE)
    if age_range_match:
        data["build_date"] = f"{age_range_match.group(1)} - {age_range_match.group(2)}"
    else:
        date_match = re.search(r'(?:Date Built|Age Range|Built)[:\s]+([0-9]{4})', combined_text, re.IGNORECASE)
        if date_match:
            data["build_date"] = date_match.group(1)
    
    if re.search(r'Timber\s+frame', combined_text, re.IGNORECASE):
        data["wall_type"] = "Timber Frame"
    elif re.search(r'Cavity', combined_text, re.IGNORECASE):
        data["wall_type"] = "Cavity Wall"
    elif re.search(r'Solid', combined_text, re.IGNORECASE):
        data["wall_type"] = "Solid Wall"
    
    storey_match = re.search(r'(?:Number of storeys|Storeys)[:\s]+([0-9]+)', combined_text, re.IGNORECASE)
    if storey_match:
        data["number_of_storeys"] = storey_match.group(1)
    
    area_match = re.search(r'(?:Area|Floor\s+0)[:\s]+([0-9]+(?:\.[0-9]+)?)\s*(?:m|m2|m²)?', combined_text, re.IGNORECASE)
    if area_match:
        data["loft_area"] = float(area_match.group(1))
        data["wall_area"] = float(area_match.group(1))
    
    if format_type == "PAS Hub":
        loft_match = re.search(r'(?:Roofs.*?Insulation Thickness|Insulation Thickness)[:\s]+([0-9]+)\s*mm', combined_text, re.IGNORECASE | re.DOTALL)
        if loft_match:
            data["loft_insulation"] = f"{loft_match.group(1)}mm"
    
    heated_rooms_match = re.search(r'(?:HEATED rooms|Heated Habitable Rooms)[:\s]+([0-9]+)', combined_text, re.IGNORECASE)
    if heated_rooms_match:
        data["heated_rooms"] = int(heated_rooms_match.group(1))
    
    wall_thickness_match = re.search(r'Wall thickness[:\s]+([0-9]+)\s*mm', combined_text, re.IGNORECASE)
    if wall_thickness_match:
        data["cavity_width"] = f"{wall_thickness_match.group(1)}mm"
    
    return data


def parse_calculation_file(calc_text: str, calc_type: str) -> Dict:
    """Parse calculation PDFs"""
    
    if calc_type == 'solar':
        data = {
            "systemSize": "",
            "systemSizeNumeric": 0,
            "manufacturer": "",
            "model": "",
            "quantity": 0,
            "inverter": "",
            "annualGeneration": ""
        }
        
        size_patterns = [
            r'Installed capacity.*?([0-9.]+)\s*kWp',
            r'(\d+\.?\d*)\s*kWp',
            r'PV power\s+(\d+\.?\d*)\s*W'
        ]
        for pattern in size_patterns:
            size_match = re.search(pattern, calc_text, re.IGNORECASE)
            if size_match:
                if 'PV power' in pattern:
                    data["systemSizeNumeric"] = float(size_match.group(1)) / 1000
                else:
                    data["systemSizeNumeric"] = float(size_match.group(1))
                data["systemSize"] = f"{data['systemSizeNumeric']} kWp"
                break
        
        panel_patterns = [
            r'(\d+)\s+([A-Za-z\s]+)\s+(\d+W)',
            r'([A-Za-z]+)\s+([A-Za-z0-9\s]+)\s+(\d+W)',
        ]
        for pattern in panel_patterns:
            panel_match = re.search(pattern, calc_text, re.IGNORECASE)
            if panel_match:
                groups = panel_match.groups()
                if len(groups) == 3 and groups[0].isdigit():
                    data["quantity"] = int(groups[0])
                    data["manufacturer"] = groups[1].strip()
                    data["model"] = f"{groups[1].strip()} {groups[2]}"
                else:
                    data["manufacturer"] = groups[0].strip()
                    data["model"] = f"{groups[0].strip()} {groups[1].strip()} {groups[2]}"
                break
        
        if data["quantity"] == 0:
            qty_match = re.search(r'Quantty\s+(\d+)', calc_text, re.IGNORECASE)
            if qty_match:
                data["quantity"] = int(qty_match.group(1))
        
        inverter_patterns = [
            r'(SolaX|Growatt|Solis|Fronius|SMA)\s+([A-Z0-9\-\s]+)\s+(\d+\.?\d*)\s*kW',
            r'Inverter.*?([A-Za-z]+\s+[A-Z0-9\-\s]+)',
        ]
        for pattern in inverter_patterns:
            inverter_match = re.search(pattern, calc_text, re.IGNORECASE)
            if inverter_match:
                data["inverter"] = inverter_match.group(0).strip()
                break
        
        gen_patterns = [
            r'Estimated output.*?(\d+)\s*kWh',
            r'Annual.*?generation.*?(\d+)\s*kWh',
            r'(\d+)\s*kWh/yr'
        ]
        for pattern in gen_patterns:
            gen_match = re.search(pattern, calc_text, re.IGNORECASE)
            if gen_match:
                data["annualGeneration"] = f"{gen_match.group(1)} kWh"
                break
        
        return data
        
    elif calc_type == 'heatpump':
        data = {
            "heatPumpSize": "",
            "heatPumpSizeNumeric": 0,
            "manufacturer": "",
            "model": "",
            "scop": "",
            "annualHeatDemand": ""
        }
        
        capacity_patterns = [
            r'Capacity\s*@\s*design.*?(\d+\.?\d*)\s*kW',
            r'Heat pump size.*?(\d+\.?\d*)\s*kW',
            r'(\d+\.?\d*)\s*kW.*?capacity'
        ]
        for pattern in capacity_patterns:
            capacity_match = re.search(pattern, calc_text, re.IGNORECASE)
            if capacity_match:
                data["heatPumpSizeNumeric"] = float(capacity_match.group(1))
                data["heatPumpSize"] = f"{capacity_match.group(1)} kW"
                break
        
        scop_match = re.search(r'SCOP\s+(\d+\.?\d*)', calc_text, re.IGNORECASE)
        if scop_match:
            data["scop"] = scop_match.group(1)
        
        demand_match = re.search(r'Demand\s+kWh/yr\s+(\d+)', calc_text, re.IGNORECASE)
        if demand_match:
            data["annualHeatDemand"] = f"{demand_match.group(1)} kWh"
        
        manufacturers = ['Mitsubishi', 'Daikin', 'Vaillant', 'Samsung', 'LG', 'Grant', 'Nibe']
        for mfr in manufacturers:
            if re.search(mfr, calc_text, re.IGNORECASE):
                data["manufacturer"] = mfr
                data["model"] = f"{mfr} Heat Pump"
                break
        
        return data
        
    elif calc_type == 'esh':
        data = {
            "manufacturer": "Elnur",
            "models": "",
            "totalHeaters": 0,
            "totalKW": 0
        }
        
        heater_patterns = [
            r'(ECOHHR\d+|PH\d+|CCB\d+)',
        ]
        
        models_list = []
        for pattern in heater_patterns:
            for match in re.finditer(pattern, calc_text):
                model = match.group(1)
                if model not in models_list:
                    models_list.append(model)
                    data["totalHeaters"] += 1
        
        data["models"] = ", ".join(models_list) if models_list else "Elnur ESH"
        
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
    
    primary_blue = colors.HexColor('#0F172A')
    accent_blue = colors.HexColor('#3B82F6')
    accent_green = colors.HexColor('#10B981')
    light_bg = colors.HexColor('#F8FAFC')
    mid_bg = colors.HexColor('#E2E8F0')
    text_mid = colors.HexColor('#475569')
    
    title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=32, textColor=primary_blue, spaceAfter=6, alignment=TA_CENTER, fontName='Helvetica-Bold', leading=38)
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Title'], fontSize=26, textColor=primary_blue, spaceAfter=24, alignment=TA_CENTER, fontName='Helvetica-Bold', leading=32)
    h1_style = ParagraphStyle('H1', parent=styles['Heading1'], fontSize=20, textColor=primary_blue, spaceAfter=16, spaceBefore=20, fontName='Helvetica-Bold', leading=24)
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=10.5, textColor=text_mid, spaceAfter=10, leading=16, alignment=TA_LEFT)
    
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


# ==================== SESSION STORAGE ====================
SESSION_STORAGE = {}

def store_session_data(user_id: int, data: Dict):
    SESSION_STORAGE[user_id] = data

def get_session_data(user_id: int) -> Optional[Dict]:
    return SESSION_STORAGE.get(user_id)

def clear_session_data(user_id: int):
    if user_id in SESSION_STORAGE:
        del SESSION_STORAGE[user_id]


# ==================== ROUTES ====================

def get_retrofit_tool_page(request: Request):
    """Entry point - upload page WITH MEASURE SHEET & VISUAL FORMAT SELECTION"""
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
        
        .format-selector {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 2rem; }}
        .format-card {{ border: 3px solid #e2e8f0; border-radius: 12px; padding: 2rem; text-align: center; cursor: pointer; transition: all 0.3s; background: white; position: relative; }}
        .format-card:hover {{ border-color: #3b82f6; transform: translateY(-2px); box-shadow: 0 4px 12px rgba(59, 130, 246, 0.2); }}
        .format-card.selected {{ border-color: #10b981; background: #ecfdf5; }}
        .format-card.selected::before {{ content: "✓"; position: absolute; top: 1rem; right: 1rem; background: #10b981; color: white; width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; }}
        .format-icon {{ font-size: 3rem; margin-bottom: 1rem; }}
        .format-name {{ font-size: 1.25rem; font-weight: 600; color: #0f172a; margin-bottom: 0.5rem; }}
        .format-desc {{ font-size: 0.9rem; color: #64748b; }}
        
        .upload-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; margin-bottom: 2rem; }}
        .upload-box {{ border: 3px dashed #cbd5e1; border-radius: 12px; padding: 2rem; text-align: center; transition: all 0.3s; cursor: pointer; background: #f8fafc; }}
        .upload-box:hover {{ border-color: #3b82f6; background: #eff6ff; }}
        .upload-box.drag-over {{ border-color: #10b981; background: #ecfdf5; }}
        .upload-box.optional {{ border-style: dotted; border-width: 2px; opacity: 0.8; }}
        .upload-icon {{ font-size: 3rem; margin-bottom: 1rem; }}
        .upload-label {{ font-size: 1.1rem; font-weight: 600; color: #0f172a; margin-bottom: 0.5rem; }}
        .upload-hint {{ font-size: 0.9rem; color: #64748b; }}
        .optional-badge {{ display: inline-block; background: #f59e0b; color: white; padding: 0.25rem 0.75rem; border-radius: 12px; font-size: 0.75rem; font-weight: 600; margin-top: 0.5rem; }}
        input[type="file"] {{ display: none; }}
        
        .form-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem; }}
        .form-group {{ margin-bottom: 1rem; }}
        label {{ display: block; font-weight: 600; margin-bottom: 0.5rem; color: #0f172a; }}
        input[type="text"], select {{ width: 100%; padding: 0.75rem; border: 2px solid #e2e8f0; border-radius: 8px; font-size: 1rem; transition: border-color 0.3s; }}
        input:focus, select:focus {{ outline: none; border-color: #3b82f6; }}
        
        .measures-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 1rem; }}
        .measure-card {{ border: 2px solid #e2e8f0; border-radius: 12px; padding: 1.5rem; text-align: center; cursor: pointer; transition: all 0.3s; background: white; }}
        .measure-card:hover {{ border-color: #3b82f6; transform: translateY(-2px); box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        .measure-card.selected {{ border-color: #10b981; background: #ecfdf5; }}
        .measure-icon {{ font-size: 2.5rem; margin-bottom: 0.5rem; }}
        .measure-name {{ font-weight: 600; color: #0f172a; }}
        .measure-checkbox {{ display: none; }}
        
        .btn {{ padding: 1rem 2rem; border: none; border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; transition: all 0.3s; }}
        .btn-primary {{ background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); color: white; }}
        .btn-primary:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4); }}
        .btn-primary:disabled {{ background: #cbd5e1; cursor: not-allowed; transform: none; }}
        .btn-secondary {{ background: #f1f5f9; color: #0f172a; }}
        .btn-secondary:hover {{ background: #e2e8f0; }}
        
        .file-status {{ margin-top: 1rem; padding: 0.5rem; border-radius: 6px; font-size: 0.9rem; }}
        .file-status.success {{ background: #d1fae5; color: #065f46; }}
        
        .info-box {{ background: #eff6ff; padding: 1rem; border-radius: 8px; margin-bottom: 1.5rem; border-left: 4px solid #3b82f6; }}
        
        @media (max-width: 768px) {{
            .upload-grid, .form-row, .format-selector {{ grid-template-columns: 1fr; }}
            .measures-grid {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>�️ Retrofit Design Tool</h1>
        <p>PAS 2035 Compliant Design Documents</p>
        <div class="credits">💳 Credits: £{credits:.2f}</div>
    </div>

    <div class="container">
        <form id="retrofitForm" method="POST" enctype="multipart/form-data">
            
            <div class="card">
                <h2 class="section-title">Step 1: Select Document Format</h2>
                <div class="info-box">
                    <strong>📋 Choose your format:</strong> Select whether you're uploading documents from Elmhurst or PAS Hub
                </div>
                
                <div class="format-selector">
                    <div class="format-card" onclick="selectFormat('elmhurst')">
                        <div class="format-icon">📊</div>
                        <div class="format-name">Elmhurst Energy</div>
                        <div class="format-desc">Elmhurst site notes & condition report</div>
                    </div>
                    <div class="format-card" onclick="selectFormat('pashub')">
                        <div class="format-icon">📑</div>
                        <div class="format-name">PAS Hub</div>
                        <div class="format-desc">PAS Hub site notes & condition report</div>
                    </div>
                </div>
            </div>
            
            <div class="card" id="uploadSection" style="display: none;">
                <h2 class="section-title">Step 2: Upload Site Documents</h2>
                <div class="info-box">
                    <strong>📄 Required:</strong> Upload 2 PDFs (Site Notes + Condition Report)<br>
                    <strong>💡 Optional:</strong> Upload Measure Data Collection Sheet as fallback source
                </div>
                
                <div class="upload-grid">
                    <div>
                        <div class="upload-box" id="siteNotesUploadBox">
                            <div class="upload-icon">📄</div>
                            <div class="upload-label" id="siteNotesLabel">Site Notes</div>
                            <div class="upload-hint">Click or drag PDF here</div>
                            <input type="file" id="siteNotesFile" name="site_notes_file" accept=".pdf">
                        </div>
                        <div id="siteNotesStatus" class="file-status" style="display:none;"></div>
                    </div>
                    
                    <div>
                        <div class="upload-box" id="conditionUploadBox">
                            <div class="upload-icon">📄</div>
                            <div class="upload-label" id="conditionLabel">Condition Report</div>
                            <div class="upload-hint">Click or drag PDF here</div>
                            <input type="file" id="conditionFile" name="condition_file" accept=".pdf">
                        </div>
                        <div id="conditionStatus" class="file-status" style="display:none;"></div>
                    </div>
                </div>
                
                <div style="text-align: center; margin-top: 1rem;">
                    <div class="upload-box optional" id="measureSheetUploadBox" style="max-width: 500px; margin: 0 auto;">
                        <div class="upload-icon">📊</div>
                        <div class="upload-label">Measure Data Collection Sheet</div>
                        <div class="upload-hint">Optional fallback source - Click or drag PDF here</div>
                        <span class="optional-badge">OPTIONAL</span>
                        <input type="file" id="measureSheetFile" name="measure_sheet_file" accept=".pdf">
                    </div>
                    <div id="measureSheetStatus" class="file-status" style="display:none;"></div>
                </div>
            </div>

            <div class="card" id="projectSection" style="display: none;">
                <h2 class="section-title">Step 3: Project Information</h2>
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

            <div class="card" id="measuresSection" style="display: none;">
                <h2 class="section-title">Step 4: Select Retrofit Measures</h2>
                <div class="measures-grid" id="measuresGrid"></div>
            </div>

            <div class="card" id="buttonSection" style="display: none; text-align: center;">
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
        const measures = {json.dumps(MEASURES)};
        let selectedMeasures = new Set();
        let selectedFormat = "";
        
        function selectFormat(format) {{
            selectedFormat = format;
            
            // Update visual selection
            document.querySelectorAll('.format-card').forEach(card => {{
                card.classList.remove('selected');
            }});
            event.currentTarget.classList.add('selected');
            
            // Show upload section
            document.getElementById('uploadSection').style.display = 'block';
            document.getElementById('projectSection').style.display = 'block';
            document.getElementById('measuresSection').style.display = 'block';
            document.getElementById('buttonSection').style.display = 'block';
            
            // Update labels
            const siteNotesLabel = document.getElementById('siteNotesLabel');
            const conditionLabel = document.getElementById('conditionLabel');
            
            if (format === 'elmhurst') {{
                siteNotesLabel.textContent = 'Elmhurst Site Notes';
                conditionLabel.textContent = 'Elmhurst Condition Report';
            }} else {{
                siteNotesLabel.textContent = 'PAS Hub Site Notes';
                conditionLabel.textContent = 'PAS Hub Condition Report';
            }}
            
            updateContinueButton();
        }}
        
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
            card.onclick = () => {{
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
            }};
            grid.appendChild(card);
        }});
        
        function updateContinueButton() {{
            const btn = document.getElementById('continueBtn');
            const hasSiteNotes = document.getElementById('siteNotesFile').files.length > 0;
            const hasCondition = document.getElementById('conditionFile').files.length > 0;
            const hasMeasures = selectedMeasures.size > 0;
            const hasFormat = selectedFormat !== "";
            btn.disabled = !(hasFormat && hasSiteNotes && hasCondition && hasMeasures);
        }}
        
        function setupUpload(boxId, inputId, statusId, required = true) {{
            const box = document.getElementById(boxId);
            const input = document.getElementById(inputId);
            const status = document.getElementById(statusId);
            
            box.onclick = () => input.click();
            
            ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(event => {{
                box.addEventListener(event, e => {{ e.preventDefault(); e.stopPropagation(); }});
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
        
        setupUpload('siteNotesUploadBox', 'siteNotesFile', 'siteNotesStatus');
        setupUpload('conditionUploadBox', 'conditionFile', 'conditionStatus');
        setupUpload('measureSheetUploadBox', 'measureSheetFile', 'measureSheetStatus', false);
        
        document.getElementById('continueBtn').onclick = async () => {{
            const formData = new FormData(document.getElementById('retrofitForm'));
            formData.append('selected_measures', JSON.stringify(Array.from(selectedMeasures)));
            formData.append('format_type', selectedFormat);
            
            const btn = document.getElementById('continueBtn');
            btn.textContent = 'Processing...';
            btn.disabled = true;
            
            try {{
                const response = await fetch('/api/retrofit-process', {{
                    method: 'POST',
                    body: formData
                }});
                
                if (response.ok) {{
                    window.location.href = '/tool/retrofit/calcs';
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


async def post_retrofit_process(request: Request):
    """Process uploaded PDFs WITH MEASURE SHEET"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    user_id = user_row["id"]
    
    try:
        form = await request.form()
        
        site_notes_file = form.get("site_notes_file")
        condition_file = form.get("condition_file")
        measure_sheet_file = form.get("measure_sheet_file")
        format_type = form.get("format_type", "PAS Hub")
        
        if not site_notes_file or not condition_file:
            return HTMLResponse("<h1>Error</h1><p>Both PDF files are required</p><a href='/tool/retrofit'>Back</a>")
        
        site_notes_bytes = await site_notes_file.read()
        condition_bytes = await condition_file.read()
        
        site_notes_text = extract_text_from_pdf(site_notes_bytes)
        condition_text = extract_text_from_pdf(condition_bytes)
        
        format_label = "PAS Hub" if format_type == "pashub" else "Elmhurst"
        extracted_data = extract_data_from_text(site_notes_text, condition_text, format_label)
        
        measure_sheet_data = {}
        if measure_sheet_file and hasattr(measure_sheet_file, 'read'):
            try:
                measure_sheet_bytes = await measure_sheet_file.read()
                if len(measure_sheet_bytes) > 0:
                    measure_sheet_text = extract_text_from_pdf(measure_sheet_bytes)
                    measure_sheet_data = parse_measure_sheet(measure_sheet_text)
            except Exception:
                pass
        
        selected_measures_json = form.get("selected_measures", "[]")
        selected_measures = json.loads(selected_measures_json)
        
        project_name = form.get("project_name", "Untitled Project")
        coordinator = form.get("coordinator", "")
        property_address = form.get("property_address", extracted_data.get("address", ""))
        
        session_data = {
            "project_name": project_name,
            "coordinator": coordinator,
            "property_address": property_address,
            "extracted_data": extracted_data,
            "selected_measures": selected_measures,
            "site_notes_text": site_notes_text,
            "condition_text": condition_text,
            "format_type": format_label,
            "current_measure_index": 0,
            "answers": {},
            "calc_data": {},
            "measure_sheet_data": measure_sheet_data
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


def get_calc_upload_page(request: Request):
    """Show calc upload page - COMPLETE WITH ALL UPLOAD BOXES"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    user_id = user_row["id"]
    session_data = get_session_data(user_id)
    
    if not session_data:
        return RedirectResponse("/tool/retrofit", status_code=303)
    
    selected_measures = session_data.get("selected_measures", [])
    
    needs_solar = "SOLAR_PV" in selected_measures
    needs_heatpump = "HEAT_PUMP" in selected_measures
    needs_esh = "ESH" in selected_measures
    
    if not (needs_solar or needs_heatpump or needs_esh):
        return RedirectResponse("/tool/retrofit/questions", status_code=303)
    
    upload_boxes_html = ""
    
    if needs_solar:
        upload_boxes_html += """
            <div>
                <div class="upload-box" id="solarCalcBox">
                    <div class="calc-icon">☀️</div>
                    <h3>Solar PV Calculation</h3>
                    <p style="color: #64748b; margin: 1rem 0;">Upload PDF to auto-populate system size, panels, inverter</p>
                    <input type="file" id="solarCalcFile" name="solar_calc_file" accept=".pdf">
                    <button type="button" class="upload-btn" onclick="document.getElementById('solarCalcFile').click()">
                        Choose PDF File
                    </button>
                </div>
                <div id="solarCalcStatus" class="file-status" style="display:none;"></div>
            </div>
        """
    
    if needs_heatpump:
        upload_boxes_html += """
            <div>
                <div class="upload-box" id="heatpumpCalcBox">
                    <div class="calc-icon">♨️</div>
                    <h3>Heat Pump Calculation</h3>
                    <p style="color: #64748b; margin: 1rem 0;">Upload PDF to auto-populate heat pump size and model</p>
                    <input type="file" id="heatpumpCalcFile" name="heatpump_calc_file" accept=".pdf">
                    <button type="button" class="upload-btn" onclick="document.getElementById('heatpumpCalcFile').click()">
                        Choose PDF File
                    </button>
                </div>
                <div id="heatpumpCalcStatus" class="file-status" style="display:none;"></div>
            </div>
        """
    
    if needs_esh:
        upload_boxes_html += """
            <div>
                <div class="upload-box" id="eshCalcBox">
                    <div class="calc-icon">🔌</div>
                    <h3>ESH Calculation</h3>
                    <p style="color: #64748b; margin: 1rem 0;">Upload PDF to auto-populate electric storage heater models</p>
                    <input type="file" id="eshCalcFile" name="esh_calc_file" accept=".pdf">
                    <button type="button" class="upload-btn" onclick="document.getElementById('eshCalcFile').click()">
                        Choose PDF File
                    </button>
                </div>
                <div id="eshCalcStatus" class="file-status" style="display:none;"></div>
            </div>
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
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8fafc; color: #0f172a; }}
        .header {{ background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: white; padding: 2rem; text-align: center; }}
        .container {{ max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }}
        .card {{ background: white; border-radius: 12px; padding: 2rem; margin-bottom: 2rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .section-title {{ font-size: 1.5rem; color: #0f172a; margin-bottom: 1.5rem; }}
        .calcs-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 2rem; }}
        .upload-box {{ border: 3px dashed #cbd5e1; border-radius: 12px; padding: 2rem; text-align: center; background: #f8fafc; }}
        .calc-icon {{ font-size: 4rem; margin-bottom: 1rem; }}
        .upload-box h3 {{ color: #0f172a; margin-bottom: 0.5rem; }}
        input[type="file"] {{ display: none; }}
        .upload-btn {{ background: #3b82f6; color: white; padding: 0.75rem 1.5rem; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; margin-top: 1rem; }}
        .upload-btn:hover {{ background: #2563eb; }}
        .file-status {{ margin-top: 1rem; padding: 0.5rem; border-radius: 6px; }}
        .file-status.success {{ background: #d1fae5; color: #065f46; }}
        .btn {{ padding: 1rem 2rem; border: none; border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; }}
        .btn-primary {{ background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); color: white; }}
        .btn-secondary {{ background: #f1f5f9; color: #0f172a; text-decoration: none; display: inline-block; }}
        .info-box {{ background: #eff6ff; padding: 1rem; border-radius: 8px; margin-bottom: 1.5rem; border-left: 4px solid #3b82f6; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Upload Calculation PDFs</h1>
        <p>Auto-populate measure data from your calculation files</p>
    </div>

    <div class="container">
        <div class="card">
            <h2 class="section-title">Calculation Files</h2>
            <div class="info-box">
                <strong>💡 Optional but recommended:</strong> Upload calculation PDFs to automatically populate measure specifications
            </div>
            
            <form id="calcForm" method="POST" enctype="multipart/form-data">
                <div class="calcs-grid">
                    {upload_boxes_html}
                </div>
                
                <div style="text-align: center; margin-top: 2rem;">
                    <button type="button" class="btn btn-primary" id="continueBtn" onclick="submitCalcs()">
                        Continue to Questions →
                    </button>
                    <a href="/tool/retrofit" class="btn btn-secondary" style="margin-left: 1rem;">
                        ← Back
                    </a>
                </div>
            </form>
        </div>
    </div>

    <script>
        const fileInputs = {{'solar': 'solarCalcFile', 'heatpump': 'heatpumpCalcFile', 'esh': 'eshCalcFile'}};
        
        Object.entries(fileInputs).forEach(([type, inputId]) => {{
            const input = document.getElementById(inputId);
            if (input) {{
                input.onchange = () => {{
                    const status = document.getElementById(type + 'CalcStatus');
                    if (input.files.length > 0) {{
                        status.style.display = 'block';
                        status.className = 'file-status success';
                        status.textContent = `✓ ${{input.files[0].name}} uploaded`;
                    }}
                }};
            }}
        }});
        
        async function submitCalcs() {{
            const formData = new FormData(document.getElementById('calcForm'));
            
            const btn = document.getElementById('continueBtn');
            btn.textContent = 'Processing...';
            btn.disabled = true;
            
            try {{
                const response = await fetch('/api/retrofit-calcs', {{
                    method: 'POST',
                    body: formData
                }});
                
                if (response.ok) {{
                    window.location.href = '/tool/retrofit/questions';
                }} else {{
                    alert('Error processing calculations');
                    btn.textContent = 'Continue to Questions →';
                    btn.disabled = false;
                }}
            }} catch (error) {{
                alert('Error: ' + error.message);
                btn.textContent = 'Continue to Questions →';
                btn.disabled = false;
            }}
        }}
    </script>
</body>
</html>
    """
    
    return HTMLResponse(html)


async def post_calc_upload(request: Request):
    """Process calculation PDFs"""
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
        
        solar_file = form.get("solar_calc_file")
        if solar_file and hasattr(solar_file, 'read'):
            solar_bytes = await solar_file.read()
            if len(solar_bytes) > 0:
                solar_text = extract_text_from_pdf(solar_bytes)
                calc_data['SOLAR_PV'] = parse_calculation_file(solar_text, 'solar')
        
        heatpump_file = form.get("heatpump_calc_file")
        if heatpump_file and hasattr(heatpump_file, 'read'):
            hp_bytes = await heatpump_file.read()
            if len(hp_bytes) > 0:
                hp_text = extract_text_from_pdf(hp_bytes)
                calc_data['HEAT_PUMP'] = parse_calculation_file(hp_text, 'heatpump')
        
        esh_file = form.get("esh_calc_file")
        if esh_file and hasattr(esh_file, 'read'):
            esh_bytes = await esh_file.read()
            if len(esh_bytes) > 0:
                esh_text = extract_text_from_pdf(esh_bytes)
                calc_data['ESH'] = parse_calculation_file(esh_text, 'esh')
        
        session_data['calc_data'] = calc_data
        store_session_data(user_id, session_data)
        
        return Response(
            content=json.dumps({"success": True}),
            media_type="application/json"
        )
        
    except Exception as e:
        return Response(
            content=json.dumps({"success": False, "error": str(e)}),
            media_type="application/json",
            status_code=500
        )


def get_questions_page(request: Request):
    """Questions page with 3-tier auto-population"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    user_id = user_row["id"]
    session_data = get_session_data(user_id)
    
    if not session_data:
        return RedirectResponse("/tool/retrofit", status_code=303)
    
    selected_measures = session_data.get("selected_measures", [])
    calc_data = session_data.get("calc_data", {})
    measure_sheet_data = session_data.get("measure_sheet_data", {})
    site_notes_text = session_data.get("site_notes_text", "")
    
    questions_html = ""
    
    for measure_code in selected_measures:
        measure = MEASURES.get(measure_code)
        if not measure:
            continue
        
        questions_html += f"""
        <div class="measure-section">
            <h3 class="measure-title">
                <span class="measure-icon">{measure['icon']}</span>
                {measure['name']}
            </h3>
            <div class="questions-grid">
        """
        
        for question in measure['questions']:
            q_id = f"{measure_code}_{question['id']}"
            
            # 3-TIER AUTO-POPULATION LOGIC
            auto_value = ""
            source_badge = ""
            
            # Priority 1: Site Notes (highest)
            if question.get('auto_populate') and site_notes_text:
                pass  # Site notes extraction would go here
            
            # Priority 2: Calc PDFs (medium)
            if not auto_value and question.get('calc_key') and measure_code in calc_data:
                calc_value = calc_data[measure_code].get(question['calc_key'], "")
                if calc_value:
                    auto_value = str(calc_value)
                    source_badge = '<span class="source-badge calc">From Calc PDF</span>'
            
            # Priority 3: Measure Sheet (fallback)
            if not auto_value and question.get('measure_sheet_key') and measure_code in measure_sheet_data:
                sheet_value = measure_sheet_data[measure_code].get(question['measure_sheet_key'], "")
                if sheet_value:
                    auto_value = str(sheet_value)
                    source_badge = '<span class="source-badge sheet">From Measure Sheet</span>'
            
            if question['type'] == 'yesno':
                yes_checked = 'checked' if auto_value.lower() == 'yes' else ''
                no_checked = 'checked' if auto_value.lower() == 'no' else ''
                questions_html += f"""
                <div class="question-item">
                    <label>{question['label']} {source_badge}</label>
                    <div class="radio-group">
                        <label><input type="radio" name="{q_id}" value="Yes" {yes_checked}> Yes</label>
                        <label><input type="radio" name="{q_id}" value="No" {no_checked}> No</label>
                    </div>
                </div>
                """
            else:
                unit_display = f" ({question.get('unit', '')})" if question.get('unit') else ""
                input_type = question.get('type', 'text')
                questions_html += f"""
                <div class="question-item">
                    <label>{question['label']}{unit_display} {source_badge}</label>
                    <input type="{input_type}" name="{q_id}" value="{auto_value}" placeholder="Enter value">
                </div>
                """
        
        questions_html += """
            </div>
        </div>
        """
    
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Measure Questions - Retrofit Tool</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8fafc; color: #0f172a; }}
        .header {{ background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: white; padding: 2rem; text-align: center; }}
        .container {{ max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }}
        .card {{ background: white; border-radius: 12px; padding: 2rem; margin-bottom: 2rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .measure-section {{ margin-bottom: 2rem; padding-bottom: 2rem; border-bottom: 2px solid #e2e8f0; }}
        .measure-title {{ font-size: 1.5rem; color: #0f172a; margin-bottom: 1.5rem; display: flex; align-items: center; gap: 0.5rem; }}
        .measure-icon {{ font-size: 2rem; }}
        .questions-grid {{ display: grid; gap: 1.5rem; }}
        .question-item label {{ display: block; font-weight: 600; margin-bottom: 0.5rem; color: #0f172a; }}
        .question-item input[type="text"], .question-item input[type="number"] {{ width: 100%; padding: 0.75rem; border: 2px solid #e2e8f0; border-radius: 8px; font-size: 1rem; }}
        .radio-group {{ display: flex; gap: 2rem; }}
        .radio-group label {{ font-weight: normal; display: flex; align-items: center; gap: 0.5rem; }}
        .source-badge {{ display: inline-block; font-size: 0.75rem; font-weight: 600; padding: 0.25rem 0.75rem; border-radius: 12px; margin-left: 0.5rem; }}
        .source-badge.calc {{ background: #d1fae5; color: #065f46; }}
        .source-badge.sheet {{ background: #fef3c7; color: #92400e; }}
        .btn {{ padding: 1rem 2rem; border: none; border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; }}
        .btn-primary {{ background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; }}
        .btn-secondary {{ background: #f1f5f9; color: #0f172a; text-decoration: none; display: inline-block; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📝 Measure Questions</h1>
        <p>Review and complete the measure specifications</p>
    </div>

    <div class="container">
        <div class="card">
            <form id="questionsForm" method="POST">
                {questions_html}
                
                <div style="text-align: center; margin-top: 2rem;">
                    <button type="submit" class="btn btn-primary">
                        Generate PDF Design 🚀
                    </button>
                    <a href="/tool/retrofit/calcs" class="btn btn-secondary" style="margin-left: 1rem;">
                        ← Back
                    </a>
                </div>
            </form>
        </div>
    </div>

    <script>
        document.getElementById('questionsForm').onsubmit = async (e) => {{
            e.preventDefault();
            const formData = new FormData(e.target);
            
            const btn = e.target.querySelector('button[type="submit"]');
            btn.textContent = 'Generating PDF...';
            btn.disabled = true;
            
            try {{
                const response = await fetch('/api/retrofit-questions', {{
                    method: 'POST',
                    body: formData
                }});
                
                if (response.ok) {{
                    window.location.href = '/api/retrofit-pdf';
                }} else {{
                    alert('Error generating PDF');
                    btn.textContent = 'Generate PDF Design 🚀';
                    btn.disabled = false;
                }}
            }} catch (error) {{
                alert('Error: ' + error.message);
                btn.textContent = 'Generate PDF Design 🚀';
                btn.disabled = false;
            }}
        }};
    </script>
</body>
</html>
    """
    
    return HTMLResponse(html)


async def post_questions_submit(request: Request):
    """Process questions and prepare PDF generation"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    user_id = user_row["id"]
    session_data = get_session_data(user_id)
    
    if not session_data:
        return RedirectResponse("/tool/retrofit", status_code=303)
    
    try:
        form = await request.form()
        answers = {}
        
        for key, value in form.items():
            if value:
                answers[key] = value
        
        session_data['answers'] = answers
        store_session_data(user_id, session_data)
        
        return Response(
            content=json.dumps({"success": True}),
            media_type="application/json"
        )
        
    except Exception as e:
        return Response(
            content=json.dumps({"success": False, "error": str(e)}),
            media_type="application/json",
            status_code=500
        )


def get_pdf_download(request: Request):
    """Generate and download PDF, deduct credits"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    user_id = user_row["id"]
    session_data = get_session_data(user_id)
    
    if not session_data:
        return RedirectResponse("/tool/retrofit", status_code=303)
    
    try:
        credits = float(user_row.get("credits", 0.0))
        if credits < RETROFIT_TOOL_COST:
            return HTMLResponse("<h1>Insufficient Credits</h1><a href='/'>Back</a>")
        
        # Build design document
        design_doc = {
            "property": {
                "address": session_data.get("property_address", ""),
                "property_type": session_data.get("extracted_data", {}).get("property_type", ""),
                "build_date": session_data.get("extracted_data", {}).get("build_date", "")
            },
            "measures": []
        }
        
        selected_measures = session_data.get("selected_measures", [])
        answers = session_data.get("answers", {})
        
        for measure_code in selected_measures:
            measure = MEASURES.get(measure_code)
            if not measure:
                continue
            
            measure_answers = []
            for question in measure['questions']:
                q_id = f"{measure_code}_{question['id']}"
                answer_value = answers.get(q_id, "")
                
                measure_answers.append({
                    "question": question['label'],
                    "answer": answer_value,
                    "unit": question.get('unit', '')
                })
            
            design_doc['measures'].append({
                "code": measure_code,
                "name": measure['name'],
                "answers": measure_answers
            })
        
        # Generate PDF
        pdf_bytes = generate_pdf_design(design_doc)
        
        # Deduct credits
        update_user_credits(user_id, -RETROFIT_TOOL_COST)
        add_transaction(user_id, -RETROFIT_TOOL_COST, "Retrofit Design Tool")
        
        # Clear session
        clear_session_data(user_id)
        
        # Return PDF
        filename = f"retrofit_design_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except Exception as e:
        return HTMLResponse(f"<h1>Error</h1><p>{str(e)}</p><a href='/'>Back</a>")
                    