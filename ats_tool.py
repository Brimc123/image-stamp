from fastapi import Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import io
from datetime import datetime
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
import pdfplumber
import re
from database import get_user_by_id, set_user_credits

templates = Jinja2Templates(directory="templates")

def create_ats_document(data):
    """Generate PAS 2035 Annex 8.2.35 compliant ATS document"""
    doc = Document()
    
    # Set default font to Calibri for entire document
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Calibri'
    font.size = Pt(11)
    
    # Title
    title = doc.add_paragraph()
    title_run = title.add_run('AIRTIGHTNESS STRATEGY')
    title_run.bold = True
    title_run.font.name = 'Calibri'
    title_run.font.size = Pt(16)
    title_run.font.color.rgb = RGBColor(0, 0, 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Subtitle
    subtitle = doc.add_paragraph()
    subtitle_run = subtitle.add_run('PAS 2035:2023 – Annex 8.2.35\nRetrofit Assessment')
    subtitle_run.font.name = 'Calibri'
    subtitle_run.font.size = Pt(12)
    subtitle_run.font.color.rgb = RGBColor(0, 0, 0)
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph()
    
    # Property Details Section
    heading = doc.add_heading('1. Property Details', level=2)
    heading.runs[0].font.name = 'Calibri'
    heading.runs[0].font.color.rgb = RGBColor(0, 0, 0)
    
    p = doc.add_paragraph()
    p.add_run('Address: ').bold = True
    p.add_run(data.get('address', '[Property Address]'))
    p.runs[0].font.name = 'Calibri'
    p.runs[1].font.name = 'Calibri'
    
    p = doc.add_paragraph()
    p.add_run('Property Type: ').bold = True
    p.add_run(data.get('property_type', 'Detached house'))
    p.runs[0].font.name = 'Calibri'
    p.runs[1].font.name = 'Calibri'
    
    p = doc.add_paragraph()
    p.add_run('Construction Type: ').bold = True
    p.add_run(data.get('construction', 'Cavity wall construction with concrete tile roof'))
    p.runs[0].font.name = 'Calibri'
    p.runs[1].font.name = 'Calibri'
    
    p = doc.add_paragraph()
    p.add_run('Age/Period: ').bold = True
    p.add_run(data.get('age', 'Post-1990s'))
    p.runs[0].font.name = 'Calibri'
    p.runs[1].font.name = 'Calibri'
    
    doc.add_paragraph()
    
    # Assessment Details Section
    heading = doc.add_heading('2. Assessment Details', level=2)
    heading.runs[0].font.name = 'Calibri'
    heading.runs[0].font.color.rgb = RGBColor(0, 0, 0)
    
    p = doc.add_paragraph()
    p.add_run('Assessor: ').bold = True
    p.add_run(data.get('assessor', '[Assessor Name]'))
    p.runs[0].font.name = 'Calibri'
    p.runs[1].font.name = 'Calibri'
    
    p = doc.add_paragraph()
    p.add_run('Inspection Date: ').bold = True
    p.add_run(data.get('inspection_date', '[Date]'))
    p.runs[0].font.name = 'Calibri'
    p.runs[1].font.name = 'Calibri'
    
    p = doc.add_paragraph()
    p.add_run('Retrofit Coordinator: ').bold = True
    p.add_run(data.get('coordinator', 'Brian McKevitt MCIOB'))
    p.runs[0].font.name = 'Calibri'
    p.runs[1].font.name = 'Calibri'
    
    p = doc.add_paragraph()
    p.add_run('PAS 2035 Compliance: ').bold = True
    p.add_run('This Airtightness Strategy is prepared in accordance with PAS 2035:2023 Annex 8.2.35')
    p.runs[0].font.name = 'Calibri'
    p.runs[1].font.name = 'Calibri'
    
    doc.add_paragraph()
    
    # Proposed Measures Section
    heading = doc.add_heading('3. Proposed Retrofit Measures', level=2)
    heading.runs[0].font.name = 'Calibri'
    heading.runs[0].font.color.rgb = RGBColor(0, 0, 0)
    
    measures_text = data.get('measures', 'Loft insulation top-up to 300mm; Solar PV installation; Heating controls upgrade')
    p = doc.add_paragraph()
    run = p.add_run(measures_text)
    run.font.name = 'Calibri'
    
    p = doc.add_paragraph()
    p.add_run('Impact on Airtightness: ').bold = True
    p.add_run('The proposed measures involve penetrations through the building envelope which may affect airtightness. This strategy ensures that airtightness is maintained or improved following the installation of these measures.')
    p.runs[0].font.name = 'Calibri'
    p.runs[1].font.name = 'Calibri'
    
    doc.add_paragraph()
    
    # Existing Airtightness Condition Section
    heading = doc.add_heading('4. Existing Airtightness Condition', level=2)
    heading.runs[0].font.name = 'Calibri'
    heading.runs[0].font.color.rgb = RGBColor(0, 0, 0)
    
    p = doc.add_paragraph()
    p.add_run('Baseline Assessment:').bold = True
    p.runs[0].font.name = 'Calibri'
    
    existing_text = data.get('existing_condition', '''• No prior airtightness test available; typical air permeability for property age and type estimated at 10-15 m³/(h.m²) at 50Pa
- Likely leakage paths identified: loft hatch perimeter, eaves junctions, service penetrations (electrical/plumbing), recessed light fittings, window and door reveals
- No persistent damp or mould observed during visual inspection
- Existing background ventilation and mechanical extract ventilation present as per original installation
- Trickle ventilators fitted to habitable rooms as per Building Regulations Part F requirements''')
    
    p = doc.add_paragraph()
    run = p.add_run(existing_text)
    run.font.name = 'Calibri'
    
    doc.add_paragraph()
    
    # Control Measures Section
    heading = doc.add_heading('5. Control Measures During Retrofit', level=2)
    heading.runs[0].font.name = 'Calibri'
    heading.runs[0].font.color.rgb = RGBColor(0, 0, 0)
    
    p = doc.add_paragraph()
    p.add_run('Air Sealing Protocols (PAS 2035:2023 Clause 8.2.35.2):').bold = True
    p.runs[0].font.name = 'Calibri'
    
    control_text = data.get('control_measures', '''
1. Loft Access and Penetrations:
   • Seal all gaps around loft hatch frame using expanding foam or flexible sealant
   • Install draught-proofing strips to loft hatch perimeter
   • Seal service penetrations through ceiling with appropriate fire-rated materials
   • Ensure insulation does not compress existing seals

2. Solar PV Installation:
   • All roof penetrations for fixings to be sealed with appropriate weatherproof sealant
   • Cable entry points through roof membrane to be sealed with grommets and sealant
   • Maintain integrity of roofing underlay

3. General Workmanship:
   • All installers briefed on airtightness requirements prior to commencement
   • Use appropriate air-sealing materials (expanding foam, acoustic sealant, tape systems)
   • Conduct visual inspection of all penetrations before covering with insulation
   • Document any unplanned penetrations and ensure proper sealing

4. Materials Specification:
   • Expanding polyurethane foam (low expansion) for large gaps
   • Acoustic-grade sealant for service penetrations
   • Self-adhesive sealing tape for joints
   • All materials to be suitable for intended application and compatible with existing construction''')
    
    p = doc.add_paragraph()
    run = p.add_run(control_text)
    run.font.name = 'Calibri'
    
    doc.add_paragraph()
    
    # Verification & Testing Section
    heading = doc.add_heading('6. Verification & Testing', level=2)
    heading.runs[0].font.name = 'Calibri'
    heading.runs[0].font.color.rgb = RGBColor(0, 0, 0)
    
    verification_text = data.get('verification', '''
Post-Installation Airtightness Testing:

- Testing Standard: ATTMA Technical Standard L1 (Measuring Air Permeability in the Existing Housing Stock)
- Target Air Permeability: ≤ 10 m³/(h.m²) at 50Pa (improvement or maintenance of existing condition)
- Testing to be conducted by ATTMA-certified air tightness tester
- Test to be performed following completion of all retrofit measures
- Results to be documented and included in project completion records

Visual Inspection Protocol:
- Pre-test visual inspection of all sealed areas
- Verification that all identified leakage paths have been addressed
- Photographic evidence of sealing works to be retained
- Any defects identified during testing to be rectified and re-tested

Acceptance Criteria:
- Air permeability result meets or improves upon baseline estimate
- No single significant leakage path identified during pressurization test
- All mechanical ventilation systems verified operational post-installation''')
    
    p = doc.add_paragraph()
    run = p.add_run(verification_text)
    run.font.name = 'Calibri'
    
    doc.add_paragraph()
    
    # Residual Risks Section
    heading = doc.add_heading('7. Residual Risks & Management', level=2)
    heading.runs[0].font.name = 'Calibri'
    heading.runs[0].font.color.rgb = RGBColor(0, 0, 0)
    
    risks_text = data.get('residual_risks', '''
Ventilation Adequacy (PAS 2035:2023 Clause 7.3):
- Risk: Improved airtightness without adequate ventilation may lead to condensation and indoor air quality issues
- Mitigation: Existing mechanical extract ventilation to remain operational; trickle ventilators to be maintained in working order
- Occupant advised to use extract fans when cooking/bathing and maintain trickle ventilator operation
- Consider future upgrade to MVHR if further airtightness improvements planned

Condensation Risk:
- Risk: Reduced air change rate may increase humidity levels
- Mitigation: Occupant guidance provided on ventilation practices; existing ventilation systems maintained
- Monitor for condensation in first heating season; respond to any issues promptly

Thermal Bridging:
- Risk: New junctions created by retrofit measures may introduce thermal bridges
- Mitigation: Insulation continuity maintained where practical; junctions detailed to minimize heat loss

Review and Monitoring:
- Initial review 3-6 months post-installation
- Annual review of building performance for 2 years
- Occupant feedback mechanism established
- Any defects or issues to be addressed promptly in accordance with warranty provisions''')
    
    p = doc.add_paragraph()
    run = p.add_run(risks_text)
    run.font.name = 'Calibri'
    
    doc.add_paragraph()
    
    # Regulatory References Section
    heading = doc.add_heading('8. Regulatory References & Standards', level=2)
    heading.runs[0].font.name = 'Calibri'
    heading.runs[0].font.color.rgb = RGBColor(0, 0, 0)
    
    references_text = data.get('references', '''
This Airtightness Strategy complies with:

- PAS 2035:2023 – Retrofitting dwellings for improved energy efficiency – Specification and guidance (Annex 8.2.35)
- PAS 2030:2019 – Improving the energy efficiency of existing buildings – Specification and guidance
- Building Regulations Approved Document L1B (2021 edition) – Conservation of fuel and power in existing dwellings
- Building Regulations Approved Document F (2021 edition) – Ventilation
- ATTMA Technical Standard L1 – Measuring Air Permeability in the Existing Housing Stock
- BS EN 13829:2001 – Thermal performance of buildings – Determination of air permeability of buildings
- CIBSE TM23 (2000) – Testing buildings for air leakage''')
    
    p = doc.add_paragraph()
    run = p.add_run(references_text)
    run.font.name = 'Calibri'
    
    doc.add_paragraph()
    doc.add_paragraph()
    
    # Footer with signatures
    p = doc.add_paragraph()
    p.add_run('Document Prepared By:').bold = True
    p.runs[0].font.name = 'Calibri'
    
    p = doc.add_paragraph(f"Retrofit Coordinator: {data.get('coordinator', 'Brian McKevitt MCIOB')}")
    p.runs[0].font.name = 'Calibri'
    
    p = doc.add_paragraph(f"Date: {datetime.now().strftime('%d/%m/%Y')}")
    p.runs[0].font.name = 'Calibri'
    
    doc.add_paragraph()
    
    # Final footer
    footer = doc.add_paragraph()
    footer_run = footer.add_run(f"Document Reference: ATS-{datetime.now().strftime('%Y%m%d')}\nGenerated: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    footer_run.font.name = 'Calibri'
    footer_run.font.size = Pt(9)
    footer_run.font.color.rgb = RGBColor(0, 0, 0)
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
            addr_pattern = re.search(r"Surveyor Name\s+([^\n]+)\s+(.+?)\s+Postcode\s+([^\n]+)", text, re.IGNORECASE | re.DOTALL)
            if addr_pattern:
                address_parts = addr_pattern.group(2).split('\n')
                address_parts = [part.strip() for part in address_parts if part.strip() and 'address' not in part.lower()]
                address_text = ', '.join(address_parts)
                postcode = addr_pattern.group(3).strip()
                parsed['address'] = f"{address_text}, {postcode}"
            
            # Extract assessor/surveyor
            assessor_match = re.search(r"(?:Assessor|Surveyor|Inspector)(?:\s*(?:Name|ID))?\s*[:\-]?\s*([A-Za-z\s.()]+)", text, re.IGNORECASE)
            if assessor_match:
                parsed['assessor'] = assessor_match.group(1).strip()
            
            # Extract inspection/survey date
            date_match = re.search(r"(?:Inspection|Survey)\s*Date\s*[:\-]?\s*([0-9]{1,2}[\/\-][0-9]{1,2}[\/\-][0-9]{2,4})", text, re.IGNORECASE)
            if date_match:
                parsed['inspection_date'] = date_match.group(1).strip()
            
            # Extract property type and construction details
            construction_keywords = {
                'cavity wall': 'Cavity wall construction',
                'solid wall': 'Solid wall construction',
                'timber frame': 'Timber framed construction',
                'system built': 'System built construction',
                'stone': 'Stone construction',
                'brick': 'Brick construction'
            }
            
            for keyword, description in construction_keywords.items():
                if re.search(keyword, text, re.IGNORECASE):
                    parsed['construction'] = description
                    break
            
            # Determine property type from context
            if re.search(r'detached|bungalow', text, re.IGNORECASE):
                if re.search(r'bungalow', text, re.IGNORECASE):
                    parsed['property_type'] = 'Detached bungalow'
                else:
                    parsed['property_type'] = 'Detached house'
            elif re.search(r'semi-detached|semi detached', text, re.IGNORECASE):
                parsed['property_type'] = 'Semi-detached house'
            elif re.search(r'terrace|terraced', text, re.IGNORECASE):
                if re.search(r'end terrace|end-terrace', text, re.IGNORECASE):
                    parsed['property_type'] = 'End-terrace house'
                else:
                    parsed['property_type'] = 'Mid-terrace house'
            elif re.search(r'flat|apartment', text, re.IGNORECASE):
                parsed['property_type'] = 'Flat/Apartment'
            
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
        user_id = user_row.get("id")
        user_data = get_user_by_id(user_id)
        balance = float(user_data.get("credits", 0.0))
        
        return templates.TemplateResponse("ats_generator.html", {
            "request": request,
            "balance": balance
        })
    
    elif request.method == "POST":
        user_id = user_row.get("id")
        user_data = get_user_by_id(user_id)
        balance = float(user_data.get("credits", 0.0))
        
        if balance < 10.00:
            return HTMLResponse(content="<h1>Insufficient balance. Please add funds.</h1>", status_code=400)
        
        form_data = await request.form()
        cr_file = form_data.get("cr_file")
        
        if not cr_file or not hasattr(cr_file, 'read'):
            return HTMLResponse(content="<h1>Please upload a Condition Report PDF</h1>", status_code=400)
        
        parsed_data = await parse_condition_report(cr_file)
        
        data = {
            'address': form_data.get('address') or parsed_data.get('address', '[Address]'),
            'property_type': form_data.get('property_type') or parsed_data.get('property_type', 'Detached house'),
            'construction': form_data.get('construction') or parsed_data.get('construction', 'Cavity wall construction'),
            'assessor': form_data.get('assessor') or parsed_data.get('assessor', '[Assessor]'),
            'inspection_date': form_data.get('inspection_date') or parsed_data.get('inspection_date', '[Date]'),
            'coordinator': form_data.get('coordinator', 'Brian McKevitt MCIOB'),
            'measures': form_data.get('measures', 'Loft insulation top-up; Solar PV; Heating controls'),
            'existing_condition': form_data.get('existing_condition') or parsed_data.get('existing_condition', ''),
        }
        
        doc = create_ats_document(data)
        
        file_stream = io.BytesIO()
        doc.save(file_stream)
        file_stream.seek(0)
        
        new_balance = balance - 10.00
        set_user_credits(user_id, new_balance)
        
        filename = f"ATS_{data.get('address', 'Property').replace(',', '').replace(' ', '_')}_Annex_8_2_35.docx"
        
        return StreamingResponse(
            file_stream,
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )