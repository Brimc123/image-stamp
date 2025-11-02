from fastapi import Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import io
from datetime import datetime
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import pdfplumber
import re
from typing import List, Optional
from database import get_user_by_id, set_user_credits

templates = Jinja2Templates(directory="templates")

# Cost for ADF Checklist generation
ADF_COST = 5.00

async def parse_ventilation_data(pdf_file):
    """Extract ventilation data from Condition Report or Site Notes PDF"""
    parsed = {
        'total_bg_vent_area': 0,
        'has_trickle_vents': False,
        'has_extract_fans': False,
        'fan_control': None,
        'vent_system': 'natural',
        'rooms': {}
    }
    
    try:
        content = await pdf_file.read()
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = "\n".join([p.extract_text() or "" for p in pdf.pages])
            
            # Extract background ventilation area (mm²)
            bg_patterns = [
                r'Background\s+Ventilation\s+Area.*?(\d+)\s*mm',
                r'Trickle\s+Vent.*?(\d+)\s*mm',
                r'Background\s+Ventilator.*?(\d+)\s*mm²'
            ]
            
            for pattern in bg_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    parsed['total_bg_vent_area'] += int(match.group(1))
            
            # Check for trickle vents
            if re.search(r'trickle\s+vent', text, re.IGNORECASE):
                parsed['has_trickle_vents'] = True
            
            # Check for extract fans
            if re.search(r'extract\s+fan', text, re.IGNORECASE):
                parsed['has_extract_fans'] = True
                
                # Determine fan control type
                if re.search(r'(pull\s+chord|manual)', text, re.IGNORECASE):
                    parsed['fan_control'] = 'manual'
                elif re.search(r'(automatic|timer|humidistat)', text, re.IGNORECASE):
                    parsed['fan_control'] = 'automatic'
            
            # Determine ventilation system type
            if re.search(r'MVHR|mechanical\s+ventilation\s+with\s+heat\s+recovery', text, re.IGNORECASE):
                parsed['vent_system'] = 'mvhr'
            elif re.search(r'continuous\s+mechanical\s+extract|CME', text, re.IGNORECASE):
                parsed['vent_system'] = 'continuous_extract'
            elif re.search(r'natural\s+ventilation', text, re.IGNORECASE):
                parsed['vent_system'] = 'natural'
                
    except Exception as e:
        print(f"Error parsing PDF: {e}")
    
    return parsed


def add_table_borders(table):
    """Add borders to table"""
    tbl = table._tbl
    tblPr = tbl.tblPr
    if tblPr is None:
        tblPr = OxmlElement('w:tblPr')
        tbl.insert(0, tblPr)
    
    tblBorders = OxmlElement('w:tblBorders')
    for border_name in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
        border = OxmlElement(f'w:{border_name}')
        border.set(qn('w:val'), 'single')
        border.set(qn('w:sz'), '4')
        border.set(qn('w:space'), '0')
        border.set(qn('w:color'), '000000')
        tblBorders.append(border)
    
    tblPr.append(tblBorders)


def generate_adf_checklist(address, vent_data):
    """Generate completed ADF Table D1 checklist document"""
    doc = Document()
    
    # Set margins
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(0.5)
        section.bottom_margin = Inches(0.5)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)
    
    # Title
    title = doc.add_paragraph()
    title_run = title.add_run('APPROVED DOCUMENT F - TABLE D1\nCHECKLIST FOR VENTILATION PROVISION IN EXISTING DWELLINGS')
    title_run.bold = True
    title_run.font.size = Pt(14)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Property details
    doc.add_paragraph()
    
    p = doc.add_paragraph()
    p.add_run('Property Address: ').bold = True
    p.add_run(address)
    
    p = doc.add_paragraph()
    p.add_run('Assessment Date: ').bold = True
    p.add_run(datetime.now().strftime('%d/%m/%Y'))
    
    doc.add_paragraph()
    
    # Determine which system to document
    system_type = vent_data.get('vent_system', 'natural')
    
    # NATURAL VENTILATION SECTION
    if system_type == 'natural':
        heading = doc.add_heading('Natural Ventilation', level=2)
        heading.runs[0].font.color.rgb = RGBColor(0, 0, 0)
        
        table = doc.add_table(rows=1, cols=3)
        add_table_borders(table)
        
        # Header row
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = 'Question'
        hdr_cells[1].text = 'Yes'
        hdr_cells[2].text = 'No'
        
        for cell in hdr_cells:
            cell.paragraphs[0].runs[0].font.bold = True
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Questions for Natural Ventilation
        questions = [
            ('What is the total equivalent area of background ventilators currently in dwelling?', 
             f"{vent_data.get('total_bg_vent_area', 0)}mm²", ''),
            
            ('Does each habitable room satisfy the minimum equivalent area standards in Table 1.7?',
             '✓' if vent_data.get('total_bg_vent_area', 0) > 0 else '', 
             '' if vent_data.get('total_bg_vent_area', 0) > 0 else '✓'),
            
            ('Have all background ventilators been left in the open position?',
             '✓' if vent_data.get('has_trickle_vents') else '', 
             '' if vent_data.get('has_trickle_vents') else '✓'),
            
            ('Are fans and background ventilators in the same room at least 0.5m apart?',
             '✓', ''),
            
            ('Are there working intermittent extract fans in all wet rooms?',
             '✓' if vent_data.get('has_extract_fans') else '', 
             '' if vent_data.get('has_extract_fans') else '✓'),
            
            ('Is there the correct number of intermittent extract fans to satisfy the standards in Table 1.1?',
             '✓' if vent_data.get('has_extract_fans') else '', 
             '' if vent_data.get('has_extract_fans') else '✓'),
            
            ('Does the location of fans satisfy the standards in paragraph 1.20?',
             '✓', ''),
            
            ('Do all automatic controls have a manual override?',
             '✓' if vent_data.get('fan_control') == 'automatic' else '', 
             '' if vent_data.get('fan_control') != 'automatic' else '✓'),
            
            ('Does each room have a system for purge ventilation (e.g. windows)?',
             '✓', ''),
            
            ('Do the openings in the rooms satisfy the minimum opening area standards in Table 1.4?',
             '✓', ''),
            
            ('Do all internal doors have sufficient undercut to allow air transfer between rooms (10mm above floor finish)?',
             '✓', ''),
        ]
        
        for question, yes_val, no_val in questions:
            row = table.add_row().cells
            row[0].text = question
            row[1].text = yes_val
            row[2].text = no_val
            
            row[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            row[2].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # CONTINUOUS MECHANICAL EXTRACT SECTION
    elif system_type == 'continuous_extract':
        heading = doc.add_heading('Continuous Mechanical Extract Ventilation', level=2)
        heading.runs[0].font.color.rgb = RGBColor(0, 0, 0)
        
        table = doc.add_table(rows=1, cols=3)
        add_table_borders(table)
        
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = 'Question'
        hdr_cells[1].text = 'Yes'
        hdr_cells[2].text = 'No'
        
        for cell in hdr_cells:
            cell.paragraphs[0].runs[0].font.bold = True
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        questions = [
            ('Does the system have a central extract fan, individual room extract fans, or both?',
             '✓', ''),
            ('Does the total combined continuous rate of mechanical extract ventilation satisfy the standards in Table 1.3?',
             '✓', ''),
            ('Does each minimum mechanical extract ventilation high rate satisfy the standards in Table 1.2?',
             '✓', ''),
            ('Is it certain that there are no background ventilators in wet rooms?',
             '✓', ''),
            ('Do all habitable rooms have a minimum equivalent area of 5000mm²?',
             '✓', ''),
            ('Does each room have a system for purge ventilation (e.g. windows)?',
             '✓', ''),
            ('Do the openings in the rooms satisfy the minimum opening area standards in Table 1.4?',
             '✓', ''),
            ('Do all internal doors have sufficient undercut (10mm above floor finish)?',
             '✓', ''),
        ]
        
        for question, yes_val, no_val in questions:
            row = table.add_row().cells
            row[0].text = question
            row[1].text = yes_val
            row[2].text = no_val
            
            row[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            row[2].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # MVHR SECTION
    elif system_type == 'mvhr':
        heading = doc.add_heading('Mechanical Ventilation with Heat Recovery (MVHR)', level=2)
        heading.runs[0].font.color.rgb = RGBColor(0, 0, 0)
        
        table = doc.add_table(rows=1, cols=3)
        add_table_borders(table)
        
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = 'Question'
        hdr_cells[1].text = 'Yes'
        hdr_cells[2].text = 'No'
        
        for cell in hdr_cells:
            cell.paragraphs[0].runs[0].font.bold = True
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        questions = [
            ('Does each habitable room have mechanical supply ventilation?',
             '✓', ''),
            ('Does the total continuous rate of mechanical ventilation with heat recovery satisfy the standards in Table 1.3?',
             '✓', ''),
            ('Does each minimum mechanical extract ventilation high rate satisfy the standards in Table 1.2?',
             '✓', ''),
            ('Have all background ventilators been removed or sealed shut?',
             '✓', ''),
            ('Does each room have a system for purge ventilation (e.g. windows)?',
             '✓', ''),
            ('Do the openings in the rooms satisfy the minimum opening area standards in Table 1.4?',
             '✓', ''),
            ('Do all internal doors have sufficient undercut (10mm above floor finish)?',
             '✓', ''),
        ]
        
        for question, yes_val, no_val in questions:
            row = table.add_row().cells
            row[0].text = question
            row[1].text = yes_val
            row[2].text = no_val
            
            row[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            row[2].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Notes
    doc.add_paragraph()
    notes = doc.add_paragraph()
    notes.add_run('NOTES:').bold = True
    doc.add_paragraph('1. Make a visual check for mould or condensation. If either are present, install additional ventilation provisions or seek specialist advice.')
    doc.add_paragraph('2. All references to tables and paragraphs are to Approved Document F, Volume 1: Dwellings.')
    
    return doc


async def adf_checklist_route(request: Request, user_row):
    """Route handler for ADF Checklist Generator"""
    if request.method == "GET":
        user_id = user_row.get("id")
        user_data = get_user_by_id(user_id)
        balance = float(user_data.get("credits", 0.0))
        return templates.TemplateResponse("adf_checklist.html", {
            "request": request, 
            "balance": balance,
            "cost": ADF_COST
        })
    
    elif request.method == "POST":
        user_id = user_row.get("id")
        user_data = get_user_by_id(user_id)
        balance = float(user_data.get("credits", 0.0))
        
        # Check balance
        if balance < ADF_COST:
            return HTMLResponse(
                content=f"<h1>Insufficient balance</h1><p>You need £{ADF_COST:.2f} but have £{balance:.2f}</p>",
                status_code=400
            )
        
        form_data = await request.form()
        address = form_data.get('address')
        
        if not address:
            return HTMLResponse(content="<h1>Please provide property address</h1>", status_code=400)
        
        # Get uploaded PDFs
        condition_report = form_data.get("condition_report")
        
        if not condition_report or not hasattr(condition_report, 'read'):
            return HTMLResponse(content="<h1>Please upload Condition Report PDF</h1>", status_code=400)
        
        # Parse Condition Report
        vent_data = await parse_ventilation_data(condition_report)
        
        # Optional Site Notes
        site_notes = form_data.get("site_notes")
        if site_notes and hasattr(site_notes, 'read'):
            site_notes_data = await parse_ventilation_data(site_notes)
            # Merge data (site notes can override condition report data)
            vent_data.update({k: v for k, v in site_notes_data.items() if v})
        
        # Generate checklist
        doc = generate_adf_checklist(address, vent_data)
        
        # Save to stream
        file_stream = io.BytesIO()
        doc.save(file_stream)
        file_stream.seek(0)
        
        # Deduct credits
        new_balance = balance - ADF_COST
        set_user_credits(user_id, new_balance)
        
        # Generate filename
        clean_address = re.sub(r'[^\w\s-]', '', address).strip().replace(' ', '_')[:50]
        filename = f"ADF_TableD1_{clean_address}.docx"
        
        return StreamingResponse(
            file_stream,
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )