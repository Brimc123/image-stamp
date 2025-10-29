from fastapi import Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import io
from datetime import datetime
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
import pdfplumber
import re
from database import get_user_by_id, set_user_credits

templates = Jinja2Templates(directory="templates")

def create_ats_document(data):
    """Generate PAS 2035 Annex 8.2.35 compliant ATS document"""
    doc = Document()
    
    # Title
    title = doc.add_paragraph()
    title_run = title.add_run('AIRTIGHTNESS STRATEGY')
    title_run.bold = True
    title_run.font.size = Pt(16)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Subtitle
    subtitle = doc.add_paragraph()
    subtitle_run = subtitle.add_run('PAS 2035:2023 – Annex 8.2.35')
    subtitle_run.font.size = Pt(12)
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph()
    
    # Property Details
    doc.add_heading('Property Details', level=2)
    doc.add_paragraph(f"Address: {data.get('address', '[Address]')}")
    doc.add_paragraph(f"Property Type: {data.get('property_type', '[Type]')}")
    doc.add_paragraph(f"Construction: {data.get('construction', '[Construction]')}")
    doc.add_paragraph()
    
    # Assessment Details
    doc.add_heading('Assessment Details', level=2)
    doc.add_paragraph(f"Assessor: {data.get('assessor', '[Assessor]')}")
    doc.add_paragraph(f"Inspection Date: {data.get('inspection_date', '[Date]')}")
    doc.add_paragraph(f"Retrofit Coordinator: {data.get('coordinator', 'Brian McKevitt MCIOB')}")
    doc.add_paragraph()
    
    # Proposed Measures
    doc.add_heading('Proposed Retrofit Measures', level=2)
    doc.add_paragraph(data.get('measures', '[Measures]'))
    doc.add_paragraph()
    
    # Existing Condition
    doc.add_heading('Existing Airtightness Condition', level=2)
    doc.add_paragraph(data.get('existing_condition', 'No prior airtightness test available.'))
    doc.add_paragraph()
    
    # Control Measures
    doc.add_heading('Control Measures During Retrofit', level=2)
    doc.add_paragraph(data.get('control_measures', 'Standard air sealing protocols to be followed during installation.'))
    doc.add_paragraph()
    
    # Verification
    doc.add_heading('Verification & Testing', level=2)
    doc.add_paragraph(data.get('verification', 'Post-retrofit airtightness test recommended per PAS 2035.'))
    doc.add_paragraph()
    
    # Residual Risks
    doc.add_heading('Residual Risks & Review', level=2)
    doc.add_paragraph(data.get('residual_risks', 'Ongoing monitoring recommended. Review within 12 months.'))
    doc.add_paragraph()
    
    # References
    doc.add_heading('Regulatory References', level=2)
    doc.add_paragraph(data.get('references', 'PAS 2035:2023, Building Regulations Part F (Ventilation), ATTMA Technical Standard L1.'))
    doc.add_paragraph()
    
    # Footer
    footer = doc.add_paragraph()
    footer_run = footer.add_run(f"Document generated: {datetime.now().strftime('%d/%m/%Y')}")
    footer_run.font.size = Pt(10)
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    return doc

async def parse_condition_report(pdf_file):
    """Extract data from Condition Report PDF"""
    parsed = {}
    
    try:
        content = await pdf_file.read()
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text_parts = []
            for page in pdf.pages:
                text_parts.append(page.extract_text() or "")
            text = "\n".join(text_parts)
            
            # DEBUG: Print extracted text
            print("=" * 80)
            print("EXTRACTED PDF TEXT:")
            print("=" * 80)
            print(text[:2000])
            print("=" * 80)
            
            # Extract address - handle multi-line format
            # Look for the pattern: Surveyor Name, then address lines, then Postcode
            addr_pattern = re.search(r"Surveyor Name\s+([^\n]+)\s+(.+?)\s+Postcode\s+([^\n]+)", text, re.IGNORECASE | re.DOTALL)
            if addr_pattern:
                # Combine all parts and clean up
                address_parts = addr_pattern.group(2).split('\n')
                address_parts = [part.strip() for part in address_parts if part.strip() and 'address' not in part.lower()]
                address_text = ', '.join(address_parts)
                postcode = addr_pattern.group(3).strip()
                parsed['address'] = f"{address_text}, {postcode}"
            
            # Extract assessor/surveyor - try multiple patterns
            assessor_match = re.search(r"(?:Assessor|Surveyor|Inspector)(?:\s*(?:Name|ID))?\s*[:\-]?\s*([A-Za-z\s.()]+)", text, re.IGNORECASE)
            if assessor_match:
                parsed['assessor'] = assessor_match.group(1).strip()
            
            # Extract inspection/survey date - try multiple patterns
            date_match = re.search(r"(?:Inspection|Survey)\s*Date\s*[:\-]?\s*([0-9]{1,2}[\/\-][0-9]{1,2}[\/\-][0-9]{2,4})", text, re.IGNORECASE)
            if date_match:
                parsed['inspection_date'] = date_match.group(1).strip()
            
            # Extract ventilation notes
            lines = [ln.strip() for ln in text.splitlines() if ln]
            v_notes = [ln for ln in lines if re.search(r"(ventilation|trickle|EA|equivalent area|fan|extract)", ln, re.IGNORECASE)]
            if v_notes:
                parsed['existing_condition'] = "• " + "\n• ".join(v_notes[:10])
                
    except Exception as e:
        print(f"Error parsing PDF: {e}")
    
    return parsed

async def ats_generator_route(request: Request, user_row):
    """Route handler for ATS Generator tool"""
    
    if request.method == "GET":
        # Show the form
        user_id = user_row.get("id")
        user_data = get_user_by_id(user_id)
        balance = float(user_data.get("credits", 0.0))
        
        return templates.TemplateResponse("ats_generator.html", {
            "request": request,
            "balance": balance
        })
    
    elif request.method == "POST":
        # Process the form
        user_id = user_row.get("id")
        user_data = get_user_by_id(user_id)
        balance = float(user_data.get("credits", 0.0))
        
        # Check balance
        if balance < 10.00:
            return HTMLResponse(content="<h1>Insufficient balance. Please add funds.</h1>", status_code=400)
        
        # Get form data
        form_data = await request.form()
        cr_file = form_data.get("cr_file")
        
        if not cr_file or not hasattr(cr_file, 'read'):
            return HTMLResponse(content="<h1>Please upload a Condition Report PDF</h1>", status_code=400)
        
        # Parse PDF
        parsed_data = await parse_condition_report(cr_file)
        
        # Build document data
        data = {
            'address': form_data.get('address') or parsed_data.get('address', '[Address]'),
            'property_type': form_data.get('property_type', '[Type]'),
            'construction': form_data.get('construction', '[Construction]'),
            'assessor': form_data.get('assessor') or parsed_data.get('assessor', '[Assessor]'),
            'inspection_date': form_data.get('inspection_date') or parsed_data.get('inspection_date', '[Date]'),
            'coordinator': form_data.get('coordinator', 'Brian McKevitt MCIOB'),
            'measures': form_data.get('measures', 'Loft insulation top-up; Solar PV; Heating controls'),
            'existing_condition': form_data.get('existing_condition') or parsed_data.get('existing_condition', ''),
            'control_measures': form_data.get('control_measures', ''),
            'verification': form_data.get('verification', ''),
            'residual_risks': form_data.get('residual_risks', ''),
            'references': form_data.get('references', '')
        }
        
        # Generate document
        doc = create_ats_document(data)
        
        # Save to BytesIO
        file_stream = io.BytesIO()
        doc.save(file_stream)
        file_stream.seek(0)
        
        # Deduct from balance
        new_balance = balance - 10.00
        set_user_credits(user_id, new_balance)
        
        # Generate filename
        filename = f"ATS_{data.get('address', 'Property').replace(',', '').replace(' ', '_')}_Annex_8_2_35.docx"
        
        return StreamingResponse(
            file_stream,
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )