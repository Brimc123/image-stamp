"""
Retrofit Design Tool - PHASES 1-3 WORKING
Phase 1: Upload (Site Notes + Condition Report + Measure Sheet)
Phase 2: Calc Upload (Solar PV, Heat Pump, ESH)
Phase 3: Questions (3-tier auto-population: Site Notes > Calcs > Measure Sheet)

FIXED: Proper UTF-8 emoji encoding
TODO: Phase 4 (Review) and Phase 5 (PDF Generation) - will add after testing
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
    """Parse Measure Design Data Collection Sheet - FALLBACK SOURCE (Priority 3)"""
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
    """Extract property data from site notes - PRIORITY 1 SOURCE"""
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
    """Parse calculation PDFs - PRIORITY 2 SOURCE"""
    
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


# ==================== SESSION STORAGE ====================
SESSION_STORAGE = {}

def store_session_data(user_id: int, data: Dict):
    SESSION_STORAGE[user_id] = data

def get_session_data(user_id: int) -> Optional[Dict]:
    return SESSION_STORAGE.get(user_id)

def clear_session_data(user_id: int):
    if user_id in SESSION_STORAGE:
        del SESSION_STORAGE[user_id]


# ==================== PHASE 1: UPLOAD PAGE ====================

def get_retrofit_tool_page(request: Request):
    """PHASE 1: Upload page with VISUAL FORMAT SELECTION + MEASURE SHEET"""
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
        <h1>🏗️ Retrofit Design Tool</h1>
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
            
            document.querySelectorAll('.format-card').forEach(card => {{
                card.classList.remove('selected');
            }});
            event.currentTarget.classList.add('selected');
            
            document.getElementById('uploadSection').style.display = 'block';
            document.getElementById('projectSection').style.display = 'block';
            document.getElementById('measuresSection').style.display = 'block';
            document.getElementById('buttonSection').style.display = 'block';
            
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
            }}
        }}
        
        setupUpload('solarCalcBox', 'solarCalcFile', 'solarCalcStatus');
        setupUpload('hpCalcBox', 'hpCalcFile', 'hpCalcStatus');
        setupUpload('eshCalcBox', 'eshCalcFile', 'eshCalcStatus');
        
        document.getElementById('calcForm').onsubmit = async (e) => {{
            e.preventDefault();
            
            const formData = new FormData(e.target);
            const submitBtn = e.target.querySelector('button[type="submit"]');
            submitBtn.textContent = 'Processing...';
            submitBtn.disabled = true;
            
            try {{
                const response = await fetch('/api/retrofit-process-calcs', {{
                    method: 'POST',
                    body: formData
                }});
                
                if (response.ok) {{
                    window.location.href = '/tool/retrofit/questions';
                }} else {{
                    alert('Error processing calculation files. Please try again.');
                    submitBtn.textContent = 'Upload & Continue →';
                    submitBtn.disabled = false;
                }}
            }} catch (error) {{
                alert('Error: ' + error.message);
                submitBtn.textContent = 'Upload & Continue →';
                submitBtn.disabled = false;
            }}
        }};
    </script>
</body>
</html>
    """
    
    return HTMLResponse(html)


async def post_retrofit_process_calcs(request: Request):
    """Process calculation PDFs - PRIORITY 2 SOURCE"""
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
        
        solar_calc_file = form.get("solar_calc_file")
        if solar_calc_file and hasattr(solar_calc_file, 'read'):
            try:
                solar_bytes = await solar_calc_file.read()
                if len(solar_bytes) > 0:
                    solar_text = extract_text_from_pdf(solar_bytes)
                    calc_data["SOLAR_PV"] = parse_calculation_file(solar_text, 'solar')
            except Exception:
                pass
        
        hp_calc_file = form.get("hp_calc_file")
        if hp_calc_file and hasattr(hp_calc_file, 'read'):
            try:
                hp_bytes = await hp_calc_file.read()
                if len(hp_bytes) > 0:
                    hp_text = extract_text_from_pdf(hp_bytes)
                    calc_data["HEAT_PUMP"] = parse_calculation_file(hp_text, 'heatpump')
            except Exception:
                pass
        
        esh_calc_file = form.get("esh_calc_file")
        if esh_calc_file and hasattr(esh_calc_file, 'read'):
            try:
                esh_bytes = await esh_calc_file.read()
                if len(esh_bytes) > 0:
                    esh_text = extract_text_from_pdf(esh_bytes)
                    calc_data["ESH"] = parse_calculation_file(esh_text, 'esh')
            except Exception:
                pass
        
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


# ==================== PHASE 3: QUESTIONS PAGE ====================

def get_retrofit_questions_page(request: Request):
    """PHASE 3: Questions page with 3-TIER AUTO-POPULATION"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    user_id = user_row["id"]
    session_data = get_session_data(user_id)
    
    if not session_data:
        return RedirectResponse("/tool/retrofit", status_code=303)
    
    selected_measures = session_data.get("selected_measures", [])
    current_index = session_data.get("current_measure_index", 0)
    extracted_data = session_data.get("extracted_data", {})
    calc_data = session_data.get("calc_data", {})
    measure_sheet_data = session_data.get("measure_sheet_data", {})
    
    if current_index >= len(selected_measures):
        return HTMLResponse("<h1>All Done!</h1><p>All questions answered.</p><p>Phase 4 (Review) and Phase 5 (PDF) coming next!</p><a href='/tool/retrofit'>Start Over</a>")
    
    current_measure_code = selected_measures[current_index]
    current_measure = MEASURES[current_measure_code]
    
    measure_calc_data = calc_data.get(current_measure_code, {})
    measure_sheet_measure_data = measure_sheet_data.get(current_measure_code, {})
    
    progress = int(((current_index) / len(selected_measures)) * 100)
    
    questions_html = ""
    for question in current_measure['questions']:
        q_id = f"{current_measure_code}_{question['id']}"
        
        auto_value = ""
        source = ""
        
        # PRIORITY 1: Site Notes
        if question.get('auto_populate'):
            if question['id'] == 'area':
                if extracted_data.get('loft_area'):
                    auto_value = str(extracted_data.get('loft_area', ''))
                    source = "Site Notes"
            elif question['id'] == 'existing':
                if extracted_data.get('loft_insulation'):
                    auto_value = extracted_data.get('loft_insulation', '')
                    source = "Site Notes"
            elif question['id'] == 'quantity':
                if extracted_data.get('heated_rooms'):
                    auto_value = str(extracted_data.get('heated_rooms', ''))
                    source = "Site Notes"
            elif question['id'] == 'width':
                if extracted_data.get('cavity_width'):
                    auto_value = extracted_data.get('cavity_width', '')
                    source = "Site Notes"
        
        # PRIORITY 2: Calculation PDFs
        if not auto_value and question.get('calc_key'):
            calc_key = question['calc_key']
            if calc_key in measure_calc_data:
                calc_value = measure_calc_data[calc_key]
                if isinstance(calc_value, (int, float)):
                    auto_value = str(calc_value)
                    source = "Calculation PDF"
                elif isinstance(calc_value, str) and calc_value:
                    auto_value = calc_value
                    source = "Calculation PDF"
        
        # PRIORITY 3: Measure Sheet (FALLBACK)
        if not auto_value and question.get('measure_sheet_key'):
            sheet_key = question['measure_sheet_key']
            if sheet_key in measure_sheet_measure_data:
                sheet_value = measure_sheet_measure_data[sheet_key]
                if sheet_value:
                    auto_value = str(sheet_value)
                    source = "Measure Sheet"
        
        source_badge = ""
        if source == "Site Notes":
            source_badge = '<span style="background: #3b82f6; color: white; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.75rem; margin-left: 0.5rem;">🔵 Site Notes</span>'
        elif source == "Calculation PDF":
            source_badge = '<span style="background: #10b981; color: white; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.75rem; margin-left: 0.5rem;">🟢 Calc PDF</span>'
        elif source == "Measure Sheet":
            source_badge = '<span style="background: #f59e0b; color: white; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.75rem; margin-left: 0.5rem;">🟡 Measure Sheet</span>'
        
        if question['type'] == 'yesno':
            checked_yes = 'checked' if auto_value.lower() in ['yes', 'y'] else ''
            checked_no = 'checked' if auto_value.lower() in ['no', 'n'] else ''
            questions_html += f"""
                <div style="margin-bottom: 2rem; padding: 1.5rem; background: #f8fafc; border-radius: 8px; border-left: 4px solid #3b82f6;">
                    <label style="display: block; font-weight: 600; margin-bottom: 1rem; color: #0f172a;">
                        {question['label']} {source_badge}
                    </label>
                    <div style="display: flex; gap: 2rem;">
                        <label style="cursor: pointer; display: flex; align-items: center; gap: 0.5rem;">
                            <input type="radio" name="{q_id}" value="Yes" {checked_yes} required>
                            <span>Yes</span>
                        </label>
                        <label style="cursor: pointer; display: flex; align-items: center; gap: 0.5rem;">
                            <input type="radio" name="{q_id}" value="No" {checked_no} required>
                            <span>No</span>
                        </label>
                    </div>
                </div>
            """
        else:
            input_type = question['type']
            unit = question.get('unit', '')
            unit_html = f'<span style="margin-left: 0.5rem; color: #64748b;">{unit}</span>' if unit else ''
            
            questions_html += f"""
                <div style="margin-bottom: 2rem;">
                    <label style="display: block; font-weight: 600; margin-bottom: 0.5rem; color: #0f172a;">
                        {question['label']} {source_badge}
                    </label>
                    <div style="display: flex; align-items: center;">
                        <input 
                            type="{input_type}" 
                            name="{q_id}" 
                            value="{auto_value}"
                            style="flex: 1; padding: 0.75rem; border: 2px solid #e2e8f0; border-radius: 8px; font-size: 1rem;"
                            placeholder="Enter {question['label'].lower()}"
                            required
                        >
                        {unit_html}
                    </div>
                </div>
            """
    
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Answer Questions - Retrofit Tool</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8fafc; color: #0f172a; }}
        .header {{ background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: white; padding: 2rem; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        .header h1 {{ font-size: 2rem; margin-bottom: 0.5rem; }}
        .progress-bar {{ width: 100%; height: 8px; background: rgba(255,255,255,0.2); border-radius: 4px; margin-top: 1rem; overflow: hidden; }}
        .progress-fill {{ height: 100%; background: #10b981; transition: width 0.3s; }}
        .container {{ max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
        .card {{ background: white; border-radius: 12px; padding: 2rem; margin-bottom: 2rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .measure-header {{ display: flex; align-items: center; gap: 1rem; margin-bottom: 2rem; padding-bottom: 1rem; border-bottom: 3px solid #3b82f6; }}
        .measure-icon {{ font-size: 3rem; }}
        .measure-title {{ font-size: 1.5rem; font-weight: 600; color: #0f172a; }}
        .btn {{ padding: 1rem 2rem; border: none; border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; transition: all 0.3s; }}
        .btn-primary {{ background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); color: white; }}
        .btn-primary:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4); }}
        .button-group {{ display: flex; gap: 1rem; justify-content: center; margin-top: 2rem; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Answer Questions</h1>
        <p>Measure {current_index + 1} of {len(selected_measures)}</p>
        <div class="progress-bar">
            <div class="progress-fill" style="width: {progress}%"></div>
        </div>
    </div>

    <div class="container">
        <div class="card">
            <div class="measure-header">
                <div class="measure-icon">{current_measure['icon']}</div>
                <div class="measure-title">{current_measure['name']}</div>
            </div>
            
            <form method="POST" action="/api/retrofit-answer">
                {questions_html}
                
                <div class="button-group">
                    <button type="submit" class="btn btn-primary">
                        Continue →
                    </button>
                </div>
            </form>
        </div>
    </div>
</body>
</html>
    """
    
    return HTMLResponse(html)


async def post_retrofit_answer(request: Request):
    """Save answers and move to next measure"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    user_id = user_row["id"]
    session_data = get_session_data(user_id)
    
    if not session_data:
        return RedirectResponse("/tool/retrofit", status_code=303)
    
    try:
        form = await request.form()
        
        selected_measures = session_data.get("selected_measures", [])
        current_index = session_data.get("current_measure_index", 0)
        current_measure_code = selected_measures[current_index]
        
        if 'answers' not in session_data:
            session_data['answers'] = {}
        
        session_data['answers'][current_measure_code] = dict(form)
        session_data['current_measure_index'] = current_index + 1
        
        store_session_data(user_id, session_data)
        
        return RedirectResponse("/tool/retrofit/questions", status_code=303)
        
    except Exception as e:
        return HTMLResponse(f"<h1>Error</h1><p>{str(e)}</p><a href='/tool/retrofit/questions'>Back</a>")
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
    """Process uploaded PDFs WITH MEASURE SHEET (Priority 3 fallback)"""
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


# ==================== PHASE 2: CALC UPLOAD ====================

def get_calc_upload_page(request: Request):
    """PHASE 2: Calc upload page (Solar PV, Heat Pump, ESH)"""
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
    
    upload_boxes = ""
    
    if needs_solar:
        upload_boxes += """
            <div>
                <div class="upload-box" id="solarCalcBox">
                    <div class="calc-icon">☀️</div>
                    <h3>Solar PV Calculation</h3>
                    <p style="color: #64748b; margin: 1rem 0;">Upload PDF to auto-populate system size, panels, inverter</p>
                    <div class="upload-hint">Click or drag PDF here</div>
                    <input type="file" id="solarCalcFile" name="solar_calc_file" accept=".pdf">
                </div>
                <div id="solarCalcStatus" class="file-status" style="display:none;"></div>
            </div>
        """
    
    if needs_heatpump:
        upload_boxes += """
            <div>
                <div class="upload-box" id="hpCalcBox">
                    <div class="calc-icon">♨️</div>
                    <h3>Heat Pump Calculation</h3>
                    <p style="color: #64748b; margin: 1rem 0;">Upload PDF to auto-populate size, manufacturer, SCOP</p>
                    <div class="upload-hint">Click or drag PDF here</div>
                    <input type="file" id="hpCalcFile" name="hp_calc_file" accept=".pdf">
                </div>
                <div id="hpCalcStatus" class="file-status" style="display:none;"></div>
            </div>
        """
    
    if needs_esh:
        upload_boxes += """
            <div>
                <div class="upload-box" id="eshCalcBox">
                    <div class="calc-icon">🔌</div>
                    <h3>ESH Calculation</h3>
                    <p style="color: #64748b; margin: 1rem 0;">Upload PDF to auto-populate heater models</p>
                    <div class="upload-hint">Click or drag PDF here</div>
                    <input type="file" id="eshCalcFile" name="esh_calc_file" accept=".pdf">
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
        .header {{ background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: white; padding: 2rem; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        .header h1 {{ font-size: 2rem; margin-bottom: 0.5rem; }}
        .container {{ max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }}
        .card {{ background: white; border-radius: 12px; padding: 2rem; margin-bottom: 2rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        
        .upload-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 2rem; margin-bottom: 2rem; }}
        .upload-box {{ border: 3px dashed #cbd5e1; border-radius: 12px; padding: 2rem; text-align: center; transition: all 0.3s; cursor: pointer; background: #f8fafc; }}
        .upload-box:hover {{ border-color: #3b82f6; background: #eff6ff; }}
        .upload-box.drag-over {{ border-color: #10b981; background: #ecfdf5; }}
        .calc-icon {{ font-size: 3rem; margin-bottom: 0.5rem; }}
        .upload-box h3 {{ color: #0f172a; margin-bottom: 0.5rem; font-size: 1.1rem; }}
        .upload-hint {{ font-size: 0.9rem; color: #64748b; margin-top: 1rem; }}
        
        .btn {{ padding: 1rem 2rem; border: none; border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; transition: all 0.3s; }}
        .btn-primary {{ background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); color: white; }}
        .btn-primary:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4); }}
        .btn-secondary {{ background: #f1f5f9; color: #0f172a; }}
        .btn-secondary:hover {{ background: #e2e8f0; }}
        
        .file-status {{ margin-top: 1rem; padding: 0.5rem; border-radius: 6px; font-size: 0.9rem; }}
        .file-status.success {{ background: #d1fae5; color: #065f46; }}
        .button-group {{ display: flex; gap: 1rem; margin-top: 2rem; justify-content: center; flex-wrap: wrap; }}
        .info-box {{ background: #eff6ff; padding: 1rem; border-radius: 8px; margin-bottom: 1.5rem; border-left: 4px solid #3b82f6; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Upload Calculation Files (Optional)</h1>
        <p>Auto-populate answers from your calculation PDFs</p>
    </div>

    <div class="container">
        <div class="card">
            <div class="info-box">
                <strong>💡 Optional Step:</strong> Upload calculation files to automatically fill in technical details. Skip if you don't have calc files - the Measure Sheet will be used as fallback.
            </div>

            <form id="calcForm" method="POST" enctype="multipart/form-data">
                <div class="upload-grid">
                    {upload_boxes}
                </div>
                
                <div class="button-group">
                    <button type="button" class="btn btn-secondary" onclick="window.location.href='/tool/retrofit/questions'">
                        Skip - Enter Manually →
                    </button>
                    <button type="submit" class="btn btn-primary">
                        Upload & Continue →
                    </button>
                </div>
            </form>
        </div>
    </div>

    <script>
        function setupUpload(boxId, inputId, statusId) {{
            const box = document.getElementById(boxId);
            const input = document.getElementById(inputId);
            const status = document.getElementById(statusId);
            
            if (!box || !input) return;
            
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
