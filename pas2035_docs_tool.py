"""
PAS 2035 Compliance Documents Generator
Generates SF48 Claim of Compliance, Customer Introduction Letter, and Handover Letter
"""

from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from datetime import datetime
import io

# Measure descriptions for letters
MEASURE_DESCRIPTIONS = {
    "RIR": "Roof Insulation and Repair",
    "IWI": "Internal Wall Insulation",
    "LOFT": "Loft Insulation",
    "GAS_BOILER": "Gas Boiler Replacement",
    "ESH": "Electric Storage Heaters",
    "ASHP": "Air Source Heat Pump",
    "SOLAR": "Solar PV Panels",
    "CWI": "Cavity Wall Insulation",
    "UFI": "Underfloor Insulation",
    "HEATING_CONTROLS": "Heating Controls Upgrade"
}

def generate_pas2035_documents(form_data: dict):
    """
    Generate all 3 PAS 2035 compliance documents
    Returns: tuple of (sf48_doc, intro_letter_doc, handover_letter_doc)
    """
    
    # Extract form data
    rc_id = form_data.get('rc_id', '')
    rc_name = form_data.get('rc_name', '')
    property_address = form_data.get('property_address', '')
    customer_name = form_data.get('customer_name', '')
    customer_address = form_data.get('customer_address', '')
    installer_name = form_data.get('installer_name', '')
    installer_contact = form_data.get('installer_contact', '')
    measures = form_data.get('measures', [])
    project_date = form_data.get('project_date', datetime.now().strftime('%d/%m/%Y'))
    install_start_date = form_data.get('install_start_date', '')
    conflict_of_interest = form_data.get('conflict_of_interest', 'No')
    
    # Convert measure codes to readable names
    measure_names = [MEASURE_DESCRIPTIONS.get(m, m) for m in measures]
    measures_text = ", ".join(measure_names)
    
    # Generate each document
    sf48_doc = generate_sf48_certificate(rc_id, rc_name, property_address, measures_text, project_date)
    intro_doc = generate_intro_letter(customer_name, customer_address, measures_text, install_start_date, installer_contact)
    handover_doc = generate_handover_letter(customer_name, customer_address, measures_text, project_date, rc_name, installer_name, conflict_of_interest)
    
    return sf48_doc, intro_doc, handover_doc


def generate_sf48_certificate(rc_id, rc_name, property_address, measures_text, project_date):
    """Generate SF48 Claim of Compliance Certificate"""
    doc = Document()
    
    # Title
    title = doc.add_heading('Retrofit Project Claim of Compliance', level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.runs[0].font.color.rgb = RGBColor(0, 102, 204)
    title.runs[0].font.size = Pt(18)
    title.runs[0].bold = True
    
    subtitle = doc.add_heading('Based on Self-assessment', level=2)
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.runs[0].font.color.rgb = RGBColor(102, 102, 102)
    
    # Introduction text
    intro = doc.add_paragraph()
    intro.add_run('This Retrofit Project undertaken at the below address and based on self-assessment was completed in accordance to ').font.size = Pt(11)
    intro.add_run('PAS 2035').bold = True
    intro.add_run(' by the below Retrofit Coordinator.').font.size = Pt(11)
    intro.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    
    doc.add_paragraph()
    
    # Create table
    table = doc.add_table(rows=6, cols=2)
    table.style = 'Light Grid Accent 1'
    
    # Fill table
    table.rows[0].cells[0].text = 'Retrofit Coordinator ID:'
    table.rows[0].cells[1].text = rc_id
    
    table.rows[1].cells[0].text = 'Retrofit Coordinator Name:'
    table.rows[1].cells[1].text = rc_name
    
    table.rows[2].cells[0].text = 'Property Address:'
    table.rows[2].cells[1].text = property_address
    
    table.rows[3].cells[0].text = 'Measures Installed:'
    table.rows[3].cells[1].text = measures_text
    
    table.rows[4].cells[0].text = 'Date:'
    table.rows[4].cells[1].text = project_date
    
    table.rows[5].cells[0].text = 'Signature:'
    table.rows[5].cells[1].text = ''
    
    # Bold first column
    for row in table.rows:
        row.cells[0].paragraphs[0].runs[0].font.bold = True
    
    return doc


def generate_intro_letter(customer_name, customer_address, measures_text, install_start_date, installer_contact):
    """Generate Customer Introduction Letter"""
    doc = Document()
    
    # Header - Energy Install Hub
    header = doc.add_paragraph()
    header_run = header.add_run('Energy Install Hub')
    header_run.bold = True
    header_run.font.size = Pt(16)
    header_run.font.color.rgb = RGBColor(0, 102, 204)
    header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Address
    address_lines = [
        '202 Queens Dock Business Centre',
        'Norfolk House',
        'Liverpool',
        'L1 0BG',
        '',
        '0800 001 6127',
        'info@energyinstallhub.co.uk'
    ]
    
    for line in address_lines:
        p = doc.add_paragraph(line)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.runs[0].font.size = Pt(10)
    
    doc.add_paragraph()
    doc.add_paragraph()
    
    # Customer details
    doc.add_paragraph(customer_name)
    for line in customer_address.split('\n'):
        doc.add_paragraph(line)
    
    doc.add_paragraph()
    doc.add_paragraph(datetime.now().strftime('%d %B %Y'))
    doc.add_paragraph()
    
    # Salutation
    doc.add_paragraph(f'Dear {customer_name},')
    doc.add_paragraph()
    
    # Body
    p1 = doc.add_paragraph()
    p1.add_run(f'We will shortly begin the installation of {measures_text} on your premises. ')
    p1.add_run('It is our intention that the installation process will be carried out in a manner that will cause you the least disruption as possible.')
    p1.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    
    doc.add_paragraph()
    
    p2 = doc.add_paragraph()
    p2.add_run(f'The date(s) we have agreed with you to carry out the work is {install_start_date}.')
    p2.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    
    doc.add_paragraph()
    
    p3 = doc.add_paragraph()
    p3.add_run('However, if other works are being carried out it can sometimes affect the timetable for our work. ')
    p3.add_run('We will keep you fully informed of any changes that may be required to be made to the timetable and will agree them with you.')
    p3.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    
    doc.add_paragraph()
    
    p4 = doc.add_paragraph()
    p4.add_run('Should you have anything you wish to discuss regarding any aspects of the installation please do not hesitate to contact me by telephone or by email.')
    p4.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    
    doc.add_paragraph()
    doc.add_paragraph('Yours faithfully')
    doc.add_paragraph()
    doc.add_paragraph('Energy Install Hub')
    
    return doc


def generate_handover_letter(customer_name, customer_address, measures_text, project_date, rc_name, installer_name, conflict_of_interest):
    """Generate Customer Handover Letter"""
    doc = Document()
    
    # Header
    header = doc.add_paragraph()
    header_run = header.add_run('Project Handover Document')
    header_run.bold = True
    header_run.font.size = Pt(16)
    header_run.font.color.rgb = RGBColor(0, 102, 204)
    header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    subtitle = doc.add_paragraph('PAS 2035 Compliant Retrofit Project')
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.runs[0].font.size = Pt(12)
    subtitle.runs[0].italic = True
    
    doc.add_paragraph()
    
    # Project Details
    doc.add_heading('Project Information', level=2)
    
    table = doc.add_table(rows=6, cols=2)
    table.style = 'Light Grid Accent 1'
    
    table.rows[0].cells[0].text = 'Customer Name:'
    table.rows[0].cells[1].text = customer_name
    
    table.rows[1].cells[0].text = 'Property Address:'
    table.rows[1].cells[1].text = customer_address.replace('\n', ', ')
    
    table.rows[2].cells[0].text = 'Measures Installed:'
    table.rows[2].cells[1].text = measures_text
    
    table.rows[3].cells[0].text = 'Completion Date:'
    table.rows[3].cells[1].text = project_date
    
    table.rows[4].cells[0].text = 'Retrofit Coordinator:'
    table.rows[4].cells[1].text = rc_name
    
    table.rows[5].cells[0].text = 'Installer:'
    table.rows[5].cells[1].text = installer_name
    
    for row in table.rows:
        row.cells[0].paragraphs[0].runs[0].font.bold = True
    
    doc.add_paragraph()
    
    # Handover Statement
    doc.add_heading('Handover Statement', level=2)
    
    p1 = doc.add_paragraph()
    p1.add_run('All retrofit measures have been installed in accordance with PAS 2035:2023 and PAS 2030:2023 standards. ')
    p1.add_run('The installation has been completed by certified installers and coordinated by a qualified Retrofit Coordinator.')
    p1.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    
    doc.add_paragraph()
    
    # User Guidance
    doc.add_heading('Using Your Improved Home', level=2)
    
    guidance = doc.add_paragraph()
    guidance.add_run('Please find enclosed all relevant user guides, warranties, and guarantees for the installed measures. ')
    guidance.add_run('We recommend you read these carefully and keep them in a safe place for future reference.')
    guidance.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    
    doc.add_paragraph()
    
    # Conflict of Interest
    doc.add_heading('Conflict of Interest Declaration', level=2)
    
    coi = doc.add_paragraph()
    coi.add_run(f'Conflict of Interest: {conflict_of_interest}')
    coi.runs[0].bold = True
    
    if conflict_of_interest.lower() == 'yes':
        coi_detail = doc.add_paragraph()
        coi_detail.add_run('Details of the conflict of interest and mitigation measures have been recorded separately in the project documentation.')
        coi_detail.runs[0].font.size = Pt(10)
        coi_detail.runs[0].italic = True
    
    doc.add_paragraph()
    doc.add_paragraph()
    
    # Signatures
    doc.add_heading('Sign-off', level=2)
    
    sig_table = doc.add_table(rows=3, cols=2)
    sig_table.rows[0].cells[0].text = 'Customer Signature:'
    sig_table.rows[1].cells[0].text = 'Retrofit Coordinator Signature:'
    sig_table.rows[2].cells[0].text = 'Date:'
    
    return doc


def save_document_to_bytes(doc):
    """Save document to bytes for download"""
    doc_io = io.BytesIO()
    doc.save(doc_io)
    doc_io.seek(0)
    return doc_io