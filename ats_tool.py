from flask import render_template, request, send_file, flash, redirect, url_for
from flask_login import login_required, current_user
import io
from datetime import datetime
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
import pdfplumber
import re
from database import db, Transaction

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

def parse_condition_report(pdf_file):
    """Extract data from Condition Report PDF"""
    parsed = {}
    
    try:
        with pdfplumber.open(pdf_file) as pdf:
            text_parts = []
            for page in pdf.pages:
                text_parts.append(page.extract_text() or "")
            text = "\n".join(text_parts)
            
            # Extract address
            addr_match = re.search(r"Property Address\s*[:\-]?\s*(.+)", text, re.IGNORECASE)
            if addr_match:
                parsed['address'] = addr_match.group(1).strip().replace("\n", " ")
            
            # Extract assessor
            assessor_match = re.search(r"Assessor(?:\s*ID|\s*name)?\s*[:\-]?\s*([A-Za-z .()/0-9]+)", text, re.IGNORECASE)
            if assessor_match:
                parsed['assessor'] = assessor_match.group(1).strip()
            
            # Extract inspection date
            date_match = re.search(r"Inspection Date\s*[:\-]?\s*([0-9]{1,2}\s*[A-Za-z]{3,9}\s*[0-9]{4}|[0-9]{2}/[0-9]{2}/[0-9]{4}|[0-9]{4}\-[0-9]{2}\-[0-9]{2})", text, re.IGNORECASE)
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

@login_required
def ats_generator_route():
    """Route handler for ATS Generator tool"""
    if request.method == 'POST':
        # Check if user has sufficient balance
        if current_user.balance < 10.00:
            flash('Insufficient balance. Please add funds.', 'error')
            return redirect(url_for('ats_generator'))
        
        # Get uploaded file
        cr_file = request.files.get('cr_file')
        
        if not cr_file:
            flash('Please upload a Condition Report PDF', 'error')
            return redirect(url_for('ats_generator'))
        
        # Parse PDF
        parsed_data = parse_condition_report(cr_file)
        
        # Get form data (overrides parsed data)
        data = {
            'address': request.form.get('address') or parsed_data.get('address', '[Address]'),
            'property_type': request.form.get('property_type', '[Type]'),
            'construction': request.form.get('construction', '[Construction]'),
            'assessor': request.form.get('assessor') or parsed_data.get('assessor', '[Assessor]'),
            'inspection_date': request.form.get('inspection_date') or parsed_data.get('inspection_date', '[Date]'),
            'coordinator': request.form.get('coordinator', 'Brian McKevitt MCIOB'),
            'measures': request.form.get('measures', 'Loft insulation top-up; Solar PV; Heating controls'),
            'existing_condition': request.form.get('existing_condition') or parsed_data.get('existing_condition', ''),
            'control_measures': request.form.get('control_measures', ''),
            'verification': request.form.get('verification', ''),
            'residual_risks': request.form.get('residual_risks', ''),
            'references': request.form.get('references', '')
        }
        
        # Generate document
        doc = create_ats_document(data)
        
        # Save to BytesIO
        file_stream = io.BytesIO()
        doc.save(file_stream)
        file_stream.seek(0)
        
        # Deduct from balance
        current_user.balance -= 10.00
        
        # Record transaction
        transaction = Transaction(
            user_id=current_user.id,
            tool='ATS Generator',
            amount=10.00,
            timestamp=datetime.utcnow()
        )
        db.session.add(transaction)
        db.session.commit()
        
        # Generate filename
        filename = f"ATS_{data.get('address', 'Property').replace(',', '').replace(' ', '_')}_Annex_8_2_35.docx"
        
        return send_file(
            file_stream,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            as_attachment=True,
            download_name=filename
        )
    
    # GET request - show form
    return render_template('ats_generator.html', balance=current_user.balance)