"""
SF70 EEM Classification Tool for AutoDate Platform
IMPROVED VERSION - Enhanced PDF Parsing with Document Type Detection
"""

from fastapi import Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, Response, RedirectResponse
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from typing import List, Dict, Optional
import re
import io
import PyPDF2


# ==================================================================================
# ENHANCED PDF PARSING FUNCTIONS - DOCUMENT TYPE DETECTION
# ==================================================================================

def extract_property_data_from_pdfs(pdf_files: List[UploadFile], provider: str = "pashub") -> Dict:
    """Extract property data from uploaded PDFs with intelligent document detection"""
    
    # Separate texts by document type
    site_notes_text = ""
    condition_report_text = ""
    all_text = ""
    
    print("\n" + "=" * 80)
    print("🔍 STARTING PDF EXTRACTION")
    print("=" * 80)
    
    for pdf_file in pdf_files:
        pdf_file.file.seek(0)
        pdf_reader = PyPDF2.PdfReader(pdf_file.file)
        
        file_text = ""
        for page in pdf_reader.pages:
            file_text += page.extract_text() + "\n"
        
        all_text += file_text
        
        # Detect document type
        if "RdSAP Assessment" in file_text or "Inspection Surveyor:" in file_text or "Floor Construction:" in file_text:
            site_notes_text += file_text
            print(f"📋 Detected SITE NOTES document: {pdf_file.filename}")
        elif "Condition Survey" in file_text or "CoreLogic" in file_text:
            condition_report_text += file_text
            print(f"📄 Detected CONDITION REPORT document: {pdf_file.filename}")
        else:
            # Unknown type - add to both
            site_notes_text += file_text
            condition_report_text += file_text
            print(f"❓ Unknown document type: {pdf_file.filename}")
    
    print("\n📊 TEXT EXTRACTION SUMMARY:")
    print(f"   Site Notes Text Length: {len(site_notes_text)} characters")
    print(f"   Condition Report Text Length: {len(condition_report_text)} characters")
    print(f"   Total Text Length: {len(all_text)} characters")
    
    # Parse based on provider and document types available
    if provider.lower() == "elmhurst":
        data = parse_elmhurst_format(all_text)
    else:
        # PasHub - use site notes primarily, enhance with condition report
        data = parse_pashub_site_notes(site_notes_text)
        enhance_with_condition_report(data, condition_report_text)
    
    print("\n✅ EXTRACTED DATA:")
    for key, value in data.items():
        if value and value != "Unknown":
            print(f"   {key}: {value}")
    
    print("=" * 80 + "\n")
    
    return data


def parse_pashub_site_notes(text: str) -> Dict:
    """Parse PasHub site notes format with specific field extraction"""
    
    data = {
        "address": "",
        "build_year": "",
        "property_type": "",
        "wall_construction": "",
        "wall_insulation": "",
        "floor_type": "",
        "floor_insulation": "",
        "roof_insulation": "",
        "roof_insulation_thickness": "",
        "window_type": "",
        "heating_system": "",
        "ventilation": [],
        "storeys": "",
        "detachment": ""
    }
    
    # Extract address (Property Address field with multi-line support)
    address_match = re.search(r'Property Address:\s*([0-9]+[^,\n]*(?:,\s*[^,\n]+)*)', text, re.IGNORECASE | re.DOTALL)
    if address_match:
        # Clean up address - remove excess whitespace
        address = address_match.group(1).strip()
        address = re.sub(r'\s+', ' ', address)  # Replace multiple spaces with single space
        data["address"] = address
        print(f"   📍 Address extracted: {address}")
    
    # Extract build year from Age Range
    build_year_match = re.search(r'Age Range:\s*(\d{4})\s*-\s*(\d{4})', text)
    if build_year_match:
        data["build_year"] = build_year_match.group(1)  # Start year
        print(f"   📅 Build year extracted: {data['build_year']}")
    
    # Extract property type
    prop_type_match = re.search(r'Type of Property:\s*([^\n]+)', text, re.IGNORECASE)
    if prop_type_match:
        data["property_type"] = prop_type_match.group(1).strip()
        print(f"   🏠 Property type extracted: {data['property_type']}")
    
    # Extract detachment type
    detach_match = re.search(r'Detachment Type:\s*([^\n]+)', text, re.IGNORECASE)
    if detach_match:
        data["detachment"] = detach_match.group(1).strip()
    
    # Extract number of storeys
    storey_match = re.search(r'Number of storeys:\s*(\d+)\s*Storey', text)
    if storey_match:
        data["storeys"] = storey_match.group(1)
    
    # Extract wall construction - SPECIFIC PATTERN
    wall_construction_match = re.search(r'Walls - Construction Type:\s*([^\n]+?)(?=\n|Walls - Insulation)', text)
    if wall_construction_match:
        data["wall_construction"] = wall_construction_match.group(1).strip()
        print(f"   🧱 Wall construction extracted: {data['wall_construction']}")
    
    # Extract wall insulation type
    wall_insulation_match = re.search(r'Walls - Insulation Type:\s*([^\n]+)', text)
    if wall_insulation_match:
        insulation_type = wall_insulation_match.group(1).strip()
        data["wall_insulation"] = insulation_type
        print(f"   🧱 Wall insulation extracted: {insulation_type}")
    
    # Extract floor construction
    floor_construction_match = re.search(r'Floor Construction:\s*([^\n]+)', text)
    if floor_construction_match:
        data["floor_type"] = floor_construction_match.group(1).strip()
        print(f"   🏗️ Floor construction extracted: {data['floor_type']}")
    
    # Extract floor insulation
    floor_insulation_match = re.search(r'Floor Insulation Type:\s*([^\n]+)', text)
    if floor_insulation_match:
        data["floor_insulation"] = floor_insulation_match.group(1).strip()
        print(f"   🏗️ Floor insulation extracted: {data['floor_insulation']}")
    
    # Extract roof insulation thickness - SPECIFIC PATTERN
    roof_thickness_match = re.search(r'Roofs - Insulation Thickness:\s*(\d+)\s*mm', text)
    if roof_thickness_match:
        data["roof_insulation_thickness"] = roof_thickness_match.group(1) + "mm"
        data["roof_insulation"] = "Yes"
        print(f"   🏠 Roof insulation extracted: {data['roof_insulation_thickness']}")
    
    # Extract roof construction
    roof_construction_match = re.search(r'Roofs - Construction Type:\s*([^\n]+?)(?=\n|Roofs - Insulation)', text)
    if roof_construction_match:
        roof_type = roof_construction_match.group(1).strip()
        if not data["roof_insulation"]:
            data["roof_insulation"] = roof_type
    
    # Extract window/glazing type - MULTIPLE PATTERNS
    glazing_patterns = [
        r'Glazing Type:\s*([^,\n]+?)(?:,|\n)',
        r'Window type:\s*([^\n]+)',
        r'Glazing type\s+([^\n]+)'
    ]
    for pattern in glazing_patterns:
        glazing_match = re.search(pattern, text, re.IGNORECASE)
        if glazing_match:
            glazing = glazing_match.group(1).strip()
            if "double" in glazing.lower():
                data["window_type"] = "Double Glazed"
            elif "single" in glazing.lower():
                data["window_type"] = "Single Glazed"
            elif "triple" in glazing.lower():
                data["window_type"] = "Triple Glazed"
            print(f"   🪟 Window type extracted: {data['window_type']}")
            break
    
    # Extract heating system - ENHANCED PATTERN
    heating_patterns = [
        r'Heating System \(Other\):\s*([^\n]+?)(?=\n[A-Z]|\nControls:)',
        r'System type:\s*([^\n]+)',
        r'Main heating\s+(?:system\s+)?:?\s*([^\n]+)'
    ]
    
    heating_systems = []
    for pattern in heating_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            system = match.group(1).strip()
            if system and system not in heating_systems:
                heating_systems.append(system)
    
    if heating_systems:
        data["heating_system"] = " + ".join(heating_systems)
        print(f"   🔥 Heating system extracted: {data['heating_system']}")
    
    # Extract ventilation
    if re.search(r'mechanical ventilation|mvhr', text, re.IGNORECASE):
        data["ventilation"].append("MVHR")
    
    # Extract fans - SPECIFIC PATTERN
    fan_match = re.search(r'Number of extract fans:\s*(\d+)', text)
    if fan_match:
        fan_count = int(fan_match.group(1))
        if fan_count > 0:
            data["ventilation"].append(f"{fan_count}x Extract Fans")
            print(f"   💨 Ventilation extracted: {fan_count}x Extract Fans")
    
    return data


def enhance_with_condition_report(data: Dict, condition_text: str):
    """Enhance data with information from condition report"""
    
    if not condition_text:
        return
    
    print("\n🔍 Enhancing with Condition Report data...")
    
    # Extract wall condition if not already detailed
    if not data.get("wall_construction") or len(data["wall_construction"]) < 10:
        wall_match = re.search(r'External Walls and DPC[:\s]+([^\n]+(?:\n(?![A-Z][a-z]+:)[^\n]+)*)', condition_text, re.IGNORECASE)
        if wall_match:
            wall_desc = wall_match.group(1).strip()
            # Only use if it adds meaningful info
            if len(wall_desc) > 20:
                data["wall_construction"] += f" - {wall_desc}" if data["wall_construction"] else wall_desc
                print(f"   🧱 Enhanced wall info from condition report")
    
    # Extract window condition
    if not data.get("window_type"):
        window_match = re.search(r'Windows and Doors[:\s]+([^\n]+(?:\n(?![A-Z][a-z]+:)[^\n]+)*)', condition_text, re.IGNORECASE)
        if window_match:
            window_desc = window_match.group(1).strip()
            if "double" in window_desc.lower():
                data["window_type"] = "Double Glazed"
                print(f"   🪟 Window type from condition report: Double Glazed")


def parse_elmhurst_format(text: str) -> Dict:
    """Parse Elmhurst-specific condition report format"""
    
    data = {
        "address": "",
        "build_year": "",
        "property_type": "",
        "wall_construction": "",
        "wall_insulation": "",
        "floor_type": "",
        "floor_insulation": "",
        "roof_insulation": "",
        "roof_insulation_thickness": "",
        "window_type": "",
        "heating_system": "",
        "ventilation": [],
        "storeys": "",
        "detachment": ""
    }
    
    # Extract address (Property Address field)
    address_match = re.search(r'Property Address[:\s]+([^\n]+(?:\n[^\n]+)*?)(?=\n\d+\.\d+|\nDate|$)', text, re.IGNORECASE)
    if address_match:
        data["address"] = address_match.group(1).strip()
    
    # Extract build year from "3.0 Date Built: Main Property"
    build_year_match = re.search(r'3\.0\s+Date Built:.*?([A-Z])\s+(\d{4})-(\d{4})', text)
    if build_year_match:
        data["build_year"] = build_year_match.group(2)  # Start year
    
    # Extract property type from "1.0 Property type:"
    prop_type_match = re.search(r'1\.0\s+Property type:\s+([A-Z])\s+([^\n]+)', text)
    if prop_type_match:
        type_code = prop_type_match.group(2).strip()
        if "House" in type_code:
            data["property_type"] = "House"
        elif "Flat" in type_code:
            data["property_type"] = "Flat"
        elif "Bungalow" in type_code:
            data["property_type"] = "Bungalow"
    
    # Extract wall construction from walls table
    wall_match = re.search(r'Type\s+([A-Z]{2,3})\s+([^\n]+)', text)
    if wall_match:
        data["wall_construction"] = wall_match.group(2).strip()
        if "Insulation" in data["wall_construction"] or "insulated" in data["wall_construction"].lower():
            data["wall_insulation"] = "Yes"
        else:
            data["wall_insulation"] = "No"
    
    # Extract window type
    window_match = re.search(r'Glazing type\s+([^\n]+)', text)
    if window_match:
        glazing = window_match.group(1).strip()
        if "double" in glazing.lower():
            data["window_type"] = "Double Glazed"
        elif "single" in glazing.lower():
            data["window_type"] = "Single Glazed"
        elif "triple" in glazing.lower():
            data["window_type"] = "Triple Glazed"
    
    # Extract heating system
    heating_match = re.search(r'Main heating\s+\d+\s+([^\n]+)', text)
    if heating_match:
        data["heating_system"] = heating_match.group(1).strip()
    
    # Extract ventilation
    if "mechanical ventilation" in text.lower() or "mvhr" in text.lower():
        data["ventilation"].append("MVHR")
    if "extract fan" in text.lower() or "extractor" in text.lower():
        data["ventilation"].append("Extract Fans")
    
    return data


def detect_retrofit_measures(property_data: Dict) -> List[str]:
    """Detect existing retrofit measures by comparing current vs build year standards"""
    
    existing_measures = []
    
    try:
        build_year = int(property_data.get("build_year", "2000"))
    except:
        build_year = 2000
    
    print(f"\n🔍 Detecting existing measures for {build_year} property...")
    
    # Wall insulation detection
    wall_construction = property_data.get("wall_construction", "").lower()
    wall_insulation = property_data.get("wall_insulation", "").lower()
    
    if "as built" in wall_insulation or "insulated" in wall_insulation or "insulation" in wall_construction:
        if "cavity" in wall_construction:
            existing_measures.append("CWI")
            print("   ✅ Detected: CWI (Cavity Wall Insulation)")
        elif "external" in wall_construction or "ewi" in wall_construction:
            existing_measures.append("EWI")
            print("   ✅ Detected: EWI (External Wall Insulation)")
        elif "internal" in wall_construction or "iwi" in wall_construction:
            existing_measures.append("IWI")
            print("   ✅ Detected: IWI (Internal Wall Insulation)")
        elif "timber frame" in wall_construction:
            # Timber frame typically has as-built insulation
            existing_measures.append("Wall Insulation (As Built)")
            print("   ✅ Detected: Timber frame with as-built insulation")
    
    # Loft insulation detection - check actual thickness
    roof_thickness = property_data.get("roof_insulation_thickness", "")
    if roof_thickness:
        thickness_match = re.search(r'(\d+)', roof_thickness)
        if thickness_match:
            thickness_mm = int(thickness_match.group(1))
            if thickness_mm >= 200:
                existing_measures.append("Loft Insulation")
                print(f"   ✅ Detected: Loft Insulation ({thickness_mm}mm)")
    elif build_year >= 2002:
        # Post-2002 properties should have 250mm+
        existing_measures.append("Loft Insulation")
        print(f"   ✅ Assumed: Loft Insulation (post-2002 property)")
    
    # Heating system upgrades
    heating = property_data.get("heating_system", "").lower()
    if "heat pump" in heating or "ashp" in heating:
        existing_measures.append("ASHP")
        print("   ✅ Detected: ASHP (Air Source Heat Pump)")
    if "storage heater" in heating:
        if "modern" in heating or "slimline" in heating or "fan" in heating:
            existing_measures.append("Modern Storage Heaters")
            print("   ✅ Detected: Modern Storage Heaters")
    if "combi" in heating or "condensing" in heating:
        existing_measures.append("Condensing Boiler")
        print("   ✅ Detected: Condensing Boiler")
    
    # Ventilation
    ventilation = property_data.get("ventilation", [])
    if "MVHR" in ventilation:
        existing_measures.append("MVHR")
        print("   ✅ Detected: MVHR (Mechanical Ventilation with Heat Recovery)")
    
    # Solar PV
    if "solar" in str(property_data).lower() or "pv" in str(property_data).lower():
        existing_measures.append("Solar PV")
        print("   ✅ Detected: Solar PV")
    
    # Windows
    window_type = property_data.get("window_type", "")
    if "double" in window_type.lower():
        # Only mention if pre-1990 property (when double glazing became standard)
        if build_year < 1990:
            existing_measures.append("Double Glazing")
            print(f"   ✅ Detected: Double Glazing (upgrade for {build_year} property)")
    
    if not existing_measures:
        print("   ℹ️  No existing retrofit measures detected")
    
    return existing_measures


def classify_sf70_path(proposed_measures: List[str]) -> str:
    """Classify SF70 path based on proposed measures"""
    
    high_risk_measures = ["EWI", "IWI", "CWI", "RIR"]
    
    proposed_high_risk = [m for m in proposed_measures if m in high_risk_measures]
    
    if not proposed_high_risk:
        return "Path A"
    elif len(proposed_high_risk) == 1:
        return "Path B"
    else:
        return "Path C"


# ==================================================================================
# REPORT GENERATION FUNCTIONS (UNCHANGED - ALREADY WORKING)
# ==================================================================================

def generate_sf70_report(property_data: Dict, proposed_measures: List[str], existing_measures: List[str]) -> bytes:
    """Generate comprehensive SF70 PDF report"""
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.75*inch, bottomMargin=0.75*inch)
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1e40af'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#1e40af'),
        spaceAfter=12,
        spaceBefore=12
    )
    
    # Title
    elements.append(Paragraph("SF70 EEM Assessment Report", title_style))
    elements.append(Paragraph("PAS 2035:2023 Compliant Assessment", styles['Normal']))
    elements.append(Spacer(1, 0.3*inch))
    
    # Property Details Table
    elements.append(Paragraph("Property Details", heading_style))
    
    property_table_data = [
        ["Address", property_data.get("address", "Not provided")],
        ["Build Year", property_data.get("build_year", "Unknown")],
        ["Property Type", property_data.get("property_type", "Unknown")],
        ["Wall Construction", property_data.get("wall_construction", "Unknown")],
        ["Window Type", property_data.get("window_type", "Unknown")],
        ["Heating System", property_data.get("heating_system", "Unknown")]
    ]
    
    property_table = Table(property_table_data, colWidths=[2*inch, 4*inch])
    property_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e0e7ff')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey)
    ]))
    
    elements.append(property_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # SF70 Path Classification
    path = classify_sf70_path(proposed_measures)
    elements.append(Paragraph(f"SF70 Path Classification: <b>{path}</b>", heading_style))
    elements.append(Paragraph(get_path_requirements(path), styles['Normal']))
    elements.append(Spacer(1, 0.2*inch))
    
    # Existing Measures
    elements.append(Paragraph("Existing Energy Efficiency Measures", heading_style))
    if existing_measures:
        for measure in existing_measures:
            elements.append(Paragraph(f"• {measure}", styles['Normal']))
    else:
        elements.append(Paragraph("No existing retrofit measures detected", styles['Normal']))
    elements.append(Spacer(1, 0.2*inch))
    
    # Page break before proposed measures
    elements.append(PageBreak())
    
    # Proposed Measures - Detailed descriptions
    elements.append(Paragraph("Proposed Measures - Detailed Assessment", heading_style))
    
    for measure in proposed_measures:
        measure_detail = get_measure_details(measure)
        elements.append(Paragraph(f"<b>{measure}</b>", styles['Heading3']))
        elements.append(Paragraph(measure_detail, styles['Normal']))
        elements.append(Spacer(1, 0.2*inch))
    
    # Page break before compliance section
    elements.append(PageBreak())
    
    # PAS 2035 Compliance Requirements
    elements.append(Paragraph("PAS 2035:2023 Compliance Requirements", heading_style))
    elements.append(Paragraph(get_building_regulations_context(), styles['Normal']))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


def get_measure_details(measure: str) -> str:
    """Get detailed description for each measure (300+ words, audit-proof)"""
    
    descriptions = {
        "EWI": "External Wall Insulation (EWI) involves applying insulation material to the external façade of the building, followed by a protective render or cladding system. This measure is considered high-risk under PAS 2035:2023 due to potential impacts on building fabric moisture management and structural loading. EWI systems typically achieve U-values of 0.18-0.30 W/m²K, representing a significant improvement over pre-1976 solid wall construction (U-value ~2.1 W/m²K). The installation requires careful assessment of existing wall tie integrity, damp-proof course detailing, and window reveals. Building Regulations Part L (2021) requires comprehensive moisture risk assessment and condensation analysis. Historical context: solid wall properties built pre-1919 used lime mortar and breathable materials; retrofit insulation must maintain vapor permeability to prevent interstitial condensation. EWI installation triggers compliance with current Part L standards, requiring assessment of thermal bridging at junctions, window reveals, and floor-to-wall interfaces. The measure qualifies as 'Major' retrofit under PAS 2035, necessitating Retrofit Designer involvement and post-installation performance evaluation.",
        
        "IWI": "Internal Wall Insulation (IWI) involves installing insulation boards or stud frame systems to the internal face of external walls, significantly reducing floor area (typically 100-150mm depth). This high-risk measure requires careful moisture management assessment as it fundamentally alters the thermal and hygroscopic behavior of the existing wall. Pre-1919 solid walls rely on outward moisture migration; IWI can trap moisture within the original structure if vapor control layers are inadequate. Building Regulations Part C (damp-proofing) and Part L (energy) both apply, requiring moisture risk modeling and condensation analysis. IWI systems achieve U-values of 0.18-0.30 W/m²K, transforming pre-1930 solid wall performance (U-value 2.0-2.5 W/m²K). Historical building regulations context: pre-1965 buildings had no insulation requirements; 1976-1990 required U-values of 1.0 W/m²K; current standards demand ≤0.30 W/m²K for retrofit. PAS 2035 mandates Retrofit Designer specification for IWI, including assessment of wall tie condition, existing damp issues, and ventilation adequacy. Post-installation monitoring is essential to verify no unintended moisture accumulation. IWI installation often necessitates relocated electrical sockets, radiator adjustments, and skirting board modifications.",
        
        "CWI": "Cavity Wall Insulation (CWI) involves injecting insulation material (mineral wool, EPS beads, or foam) into the existing cavity between inner and outer wall leaves. Classified as high-risk under PAS 2035:2023, CWI requires pre-installation assessment of cavity width (minimum 50mm), wall tie condition, and exposure to wind-driven rain. Properties built 1920-1990 typically feature unfilled cavities (U-value 1.0-1.5 W/m²K); CWI reduces this to 0.30-0.55 W/m²K depending on cavity width and fill material. Historical context: cavity walls were introduced around 1920 to prevent rain penetration; the cavity was never intended as thermal insulation. Building Regulations Part L first required cavity insulation in 1990; Part C addresses moisture risks. CWI installation must comply with BS 5618 (mineral wool) or BBA certified systems. High exposure zones (>56.5 liters/m² wind-driven rain) may be unsuitable for CWI; BRE recommendations advise against CWI in severe exposure areas. PAS 2035 requires borescope cavity inspection, minimum two cavity widths assessment, and verification of wall tie integrity. Existing damp issues, bridged cavities, or narrow cavities (<50mm) are contraindications. Post-installation thermal imaging verification ensures complete fill without voids. CWI qualifies as a 'Major' measure, requiring Retrofit Coordinator oversight.",
        
        "RIR": "Room-in-Roof (RIR) insulation addresses the unique thermal geometry of converted loft spaces, where sloping ceilings create complex junctions between heated and unheated spaces. This high-risk measure requires careful treatment of thermal bridging, air-tightness, and moisture control. RIR spaces typically combine sloping roof sections (requiring rafter-level insulation), vertical knee walls, and flat ceiling areas. Pre-2002 RIR conversions often have inadequate insulation (U-value 0.6-1.5 W/m²K); current Building Regulations Part L requires ≤0.16 W/m²K for roof elements. The retrofit challenge involves achieving target U-values while maintaining ventilation pathways above insulation (25-50mm air gap) and managing condensation risk. PAS 2035 classifies RIR as high-risk due to complex detailing requirements: eaves ventilation, party wall fire stopping, service penetration sealing, and junction detailing at roof-to-wall interfaces. Moisture risk is significant: warm, moist internal air can migrate through gaps into cold roof spaces, causing condensation on sarking felt or timber. Vapor control layers (VCL) must be continuous and air-tight; service penetrations for lighting and electrical require careful sealing. Historical building regulations context: 1965-1985 required minimal roof insulation (U-value 1.0 W/m²K); 1990-2002 required 0.25 W/m²K; 2006-2021 required 0.16 W/m²K; current standards maintain 0.16 W/m²K for retrofits. RIR insulation installation requires Retrofit Designer specification, air-tightness testing post-installation, and thermal imaging verification.",
        
        "Loft Insulation": "Loft insulation upgrade involves increasing insulation depth in accessible roof spaces to achieve current Building Regulations standards of 270-300mm (U-value ≤0.16 W/m²K). This measure is considered lower-risk but requires attention to ventilation, condensation risk, and service protection. Historical context: pre-1965 properties typically have zero loft insulation; 1965-1975 required 25mm (U-value 1.5 W/m²K); 1976-1990 required 100mm (U-value 0.6 W/m²K); 1990-2002 required 150mm (U-value 0.25 W/m²K); 2002-2006 required 250mm (U-value 0.16 W/m²K). Properties built pre-1990 are candidates for loft insulation upgrade. Retrofit considerations include: maintaining 25mm ventilation gap at eaves to prevent interstitial condensation; protecting electrical cables (which can overheat if buried); creating insulation-free zones around recessed lighting (50mm clearance); and installing loft hatches with insulated, draught-sealed covers. PAS 2035 requires assessment of existing ventilation adequacy, condition of roof structure and covering, and presence of cold-water tanks requiring frost protection. Vapor control is critical: warm, moist air migrating into cold loft spaces condenses on cold surfaces. Cross-ventilation (eaves-to-eaves or eaves-to-ridge) of 10mm continuous gap per meter span is required. Party walls in semi-detached or terraced properties require fire-stopping at loft level. Loft insulation qualifies as 'Minor' retrofit but requires Retrofit Assessor specification to ensure adequate ventilation and condensation risk management.",
        
        "Heating Controls": "Heating control upgrades include thermostatic radiator valves (TRVs), smart thermostats, zone controls, weather compensation, and time scheduling. These measures optimize heating system efficiency by matching heat output to occupancy patterns and external conditions. Building Regulations Part L (2021) requires, as minimum standard: room thermostats, TRVs on all radiators except the room with the room thermostat, programmer or time switch for space heating, and separate controls for hot water in systems with storage cylinders. Retrofit projects upgrading heating systems must meet these standards. Smart thermostats with internet connectivity and occupancy detection can achieve 10-20% energy savings compared to basic controls. Weather compensation adjusts boiler flow temperature based on external temperature, improving condensing boiler efficiency (additional 5-8% savings). Zoning allows independent temperature control of different property areas, reducing energy waste in unused spaces. PAS 2035 considers heating control upgrades as 'Minor' measures but emphasizes the importance of user education: poorly understood controls can negate efficiency benefits. Historical context: pre-1985 heating systems rarely had TRVs or programmers; 1985-2005 saw gradual introduction of basic controls; current standards mandate comprehensive control systems. Heating control retrofits should include: TRVs on all radiators (except room with room thermostat); smart thermostat with weather compensation; separate hot water timing; and user guidance documentation. Integration with smart home systems enables remote control and occupancy-based scheduling.",
        
        "Boiler Upgrade": "Boiler replacement with a modern condensing combi boiler achieves significant efficiency improvements over pre-2005 non-condensing systems. Historical boiler efficiency context: pre-1980 boilers achieved 60-65% seasonal efficiency; 1980-1998 improved to 70-75%; 1998-2005 non-condensing boilers reached 75-80%; post-2005 condensing boilers achieve 88-94% efficiency. Building Regulations Part L (2005 onwards) requires condensing boilers for all replacements. Modern condensing boilers extract additional heat from flue gases by condensing water vapor, achieving efficiencies of 90%+ at lower flow temperatures. Optimal performance requires: weather compensation controls; low return temperatures (<55°C); adequate system volume and flow rates; and regular maintenance. PAS 2035 categorizes boiler replacement as 'Moderate' measure, requiring Retrofit Assessor involvement to ensure: correct sizing (avoiding oversizing which reduces efficiency); compatibility with existing heating distribution system; adequate ventilation for combustion air; and appropriate flue routing. Boiler upgrades should be coordinated with fabric improvements (insulation) to avoid oversizing. Modern boilers are sized based on heat loss calculations incorporating fabric improvements; pre-1980 boilers were typically oversized by 50-100%. Condensing boiler installation requires: condensate drain (pH-neutral discharge); room-sealed balanced flue or adequate ventilation; magnetic system filter to protect heat exchanger; and system flush to remove debris. Building Regulations Part J addresses combustion appliance safety; Part F addresses ventilation. The installer must provide user operating instructions and commissioning documentation showing correct setup of controls.",
        
        "ASHP": "Air Source Heat Pump (ASHP) installation represents a fundamental transition from fossil fuel combustion to electric heat distribution, with significant implications for heating system design and building fabric performance. ASHPs extract ambient heat from external air and concentrate it for space and water heating, achieving seasonal performance factors (SPF) of 250-350% (i.e., 1 kWh electricity produces 2.5-3.5 kWh heat output). Optimal ASHP performance requires: low flow temperatures (35-45°C) achieved through larger radiators or underfloor heating; excellent building fabric insulation minimizing heat demand; and continuous heating operation rather than on/off cycling. Building Regulations Part L (2021) permits ASHP retrofit without fabric upgrades but poor fabric performance results in low SPF and high running costs. PAS 2035 treats ASHP as 'Major' measure requiring: detailed heat loss calculation considering fabric improvements; radiator sizing assessment (larger radiators needed for low flow temperatures); hot water cylinder specification (250+ liter cylinder with high-performance coil); electrical supply upgrade assessment (typical 16-32A requirement); and noise impact assessment for external unit positioning. Historical heating system context: pre-1980 systems operated at 70-80°C flow temperatures; 1980-2005 reduced to 65-75°C; modern condensing boilers optimize at 55-65°C; ASHPs require 35-50°C. Achieving these temperatures in older properties requires: radiator upgrades (increasing surface area by 50-100%); improved insulation reducing heat demand; and possibly underfloor heating installation. ASHP installation requires Microgeneration Certification Scheme (MCS) certification for renewable heat incentive eligibility. The system design must include: weather compensation controls; buffer tank (often required); system volume calculation ensuring adequate water content; and defrost cycle accommodation. User education is critical: ASHP systems operate differently from boilers (continuous low-level heating vs. on-demand high heat).",
        
        "Solar PV": "Solar photovoltaic (PV) installation converts sunlight directly into electricity, reducing grid electricity consumption and carbon emissions. System sizing considerations include: available roof area (typically 1.5-2.5m² per kWp); roof orientation (south-facing optimal, east/west acceptable); roof pitch (30-45° optimal); and shading analysis (chimneys, trees, adjacent buildings reduce output significantly). A typical 4kWp system (16-20 panels) generates 3,400-3,800 kWh annually in the UK, covering 50-80% of typical household electricity demand (3,800-4,200 kWh). Building Regulations Part P (electrical safety) applies to PV installation; Part L includes solar PV in energy performance calculations. MCS certification is required for Smart Export Guarantee (SEG) payments. PAS 2035 treats solar PV as 'Moderate' measure requiring: structural assessment of roof loading (additional 10-15 kg/m²); electrical installation design complying with BS 7671; DNO (Distribution Network Operator) notification for systems >3.68kWp; and Fire Safety guidance compliance (fire service roof access). Historical energy context: pre-2000 properties have high electricity demand for lighting and appliances; LED lighting and efficient appliances reduce demand by 30-40%; remaining electricity consumption (space heating, hot water, cooking, appliances) can be partially offset by solar PV. System components include: PV panels (monocrystalline most efficient, polycrystalline more economical); inverter (string inverter for simple roof layouts, micro-inverters for complex shading); generation meter; and grid connection protection. Battery storage integration (5-10kWh capacity) increases self-consumption from 30-40% to 60-70%, improving economic return. PV installation requires: roof structural survey confirming adequate load capacity; electrical design incorporating surge protection; scaffolding for safe access; and post-installation commissioning documentation. The installer must provide: predicted generation estimates based on shading analysis; system warranty details; and guidance on monitoring and maintenance.",
        
        "ESH HHR": "Electric Storage Heaters with High Heat Retention (ESH HHR) utilize advanced ceramic core materials and improved insulation to store heat during off-peak electricity periods and release it gradually throughout the day. Modern HHR storage heaters achieve significantly improved efficiency and control compared to pre-1990 storage heaters. Historical context: pre-1980 storage heaters were basic with minimal insulation (20-30% heat loss overnight); 1980-2000 models improved insulation but had limited control; post-2018 Lot 20 compliant HHR models feature: electronic charge control, programmable room thermostats, open window detection, and adaptive start. Building Regulations Part L requires, for electric heating systems, SAP calculations demonstrating reasonable heating costs; storage heaters benefit from Economy 7 tariffs but require careful sizing to avoid overheating or underheating. PAS 2035 considers storage heater replacement as 'Moderate' measure requiring: electrical supply assessment (adequate circuit capacity); user behavior assessment (occupancy patterns must suit timed charging); and tariff analysis (Economy 7 or Economy 10 tariffs essential for cost-effective operation). Modern HHR storage heaters include: fan-assisted heat release for responsive heating; electronic charge control adjusting stored heat based on predicted requirements; and room thermostats preventing overheating. Retrofit considerations include: adequate electrical circuit capacity (16-32A per heater depending on size); time switch or smart meter for off-peak charging control; and insulation improvements to reduce heat demand (storage heaters in poorly insulated properties result in high running costs). Storage heater sizing requires heat loss calculation accounting for building fabric; oversized heaters waste energy through excess charging; undersized heaters provide inadequate warmth. User guidance is critical: occupants must understand charge control settings, timing requirements, and the delayed heat response characteristic of storage systems."
    }
    
    return descriptions.get(measure, f"Detailed technical assessment required for {measure} installation considering building fabric, existing services, and PAS 2035:2023 compliance requirements.")


def get_path_requirements(path: str) -> str:
    """Get PAS 2035 compliance requirements for each path"""
    
    path_requirements = {
        "Path A": "Path A projects (no high-risk measures) require a Retrofit Assessor to conduct initial assessment, specify measures, and produce the Retrofit Plan. A Retrofit Coordinator oversees the project to ensure measures are installed as designed and conducts post-installation evaluation. No Retrofit Designer is required for Path A.",
        
        "Path B": "Path B projects (single high-risk measure) require a Retrofit Assessor to conduct the initial assessment and a Retrofit Designer to provide detailed specifications for the high-risk measure, including moisture risk assessment, ventilation strategy, and construction detailing. A Retrofit Coordinator oversees the entire project, ensuring design compliance and conducting post-installation evaluation.",
        
        "Path C": "Path C projects (multiple high-risk measures or complex whole-house retrofits) require comprehensive professional oversight: Retrofit Assessor conducts detailed building assessment; Retrofit Designer produces full technical specifications, construction drawings, and risk assessments for all measures; Retrofit Coordinator manages the entire project ensuring design intent is achieved, coordinates multiple trades, and conducts rigorous post-installation evaluation with performance testing."
    }
    
    return path_requirements.get(path, "PAS 2035:2023 compliance assessment required.")


def get_building_regulations_context() -> str:
    """Provide historical building regulations context for retrofit measures"""
    
    return """Building Regulations Historical Context for Retrofit Measures:

UK Building Regulations have evolved significantly since their introduction, with insulation standards improving dramatically over decades. Understanding this historical context is essential for retrofit assessment:

Pre-1965: No thermal insulation requirements existed. Properties from this era typically feature solid walls (U-value ~2.1 W/m²K), single glazing (U-value ~5.0 W/m²K), and uninsulated roofs (U-value ~2.5 W/m²K). Total fabric heat loss in pre-1965 properties is typically 200-300 W/K for a typical house.

1965-1975: First insulation standards introduced. Roof insulation of 25mm required (U-value 1.5 W/m²K). Wall standards remained unchanged. This period represents the beginning of energy awareness following the 1973 oil crisis.

1976-1990: Significant improvements. Roof insulation increased to 100mm (U-value 0.6 W/m²K). Cavity walls required insulation (U-value 1.0 W/m²K). Double glazing became more common but was not mandatory.

1990-1995: Building Regulations Part L introduced comprehensive energy standards. Roof insulation increased to 150mm (U-value 0.25 W/m²K). Wall U-values reduced to 0.45 W/m²K. Windows required to achieve U-value 3.3 W/m²K.

1995-2002: Part L revised with area-weighted U-value calculations. Roof standards improved to U-value 0.25 W/m²K. Wall standards tightened to 0.35 W/m²K. Window standards improved to U-value 2.2 W/m²K.

2002-2006: Major Part L revision. Roof insulation increased to 270mm (U-value 0.16 W/m²K). Wall U-values reduced to 0.30 W/m²K. Double glazing became effectively mandatory (U-value 2.0 W/m²K). Air-tightness testing introduced for new builds.

2006-2010: Carbon compliance emphasis. Roof U-values maintained at 0.16 W/m²K. Wall standards improved to 0.28 W/m²K. Windows required U-value 1.8 W/m²K. Condensing boilers became mandatory.

2010-2013: Further incremental improvements with fabric energy efficiency targets. Whole-house approach to energy performance rather than individual element compliance.

2013-2021: Part L focus on cost-optimal efficiency levels balancing carbon reduction with economic viability. Roof 0.16 W/m²K, walls 0.28 W/m²K, windows 1.6 W/m²K. Renewable technologies encouraged.

2021-present: Future Homes Standard preparation. Part L 2021 raised new build standards by ~30% carbon reduction compared to 2013. Retrofit standards maintain 0.16 W/m²K for roofs, 0.30 W/m²K for walls when renovating. PAS 2035:2023 provides comprehensive retrofit framework addressing unintended consequences of poorly planned retrofits.

Retrofit projects must comply with Part L when renovating thermal elements over 50% of surface area or when adding new thermal elements. Part C (moisture control), Part F (ventilation), and Part J (combustion appliances) also apply. PAS 2035:2023 emphasizes the 'fabric first' approach: optimize building envelope before installing efficient heating systems."""


# ==================================================================================
# HTML INTERFACE (UNCHANGED)
# ==================================================================================

def get_sf70_html(error: str = None) -> str:
    """Generate beautiful HTML interface with blue gradient theme and two upload boxes"""
    
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>🔥 SF70 EEM Assessment Tool - AutoDate</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background: linear-gradient(135deg, #0F2027 0%, #203A43 30%, #2C5364 100%);
                min-height: 100vh;
                padding: 40px 20px;
            }
            
            .container { max-width: 1000px; margin: 0 auto; }
            
            .header { text-align: center; margin-bottom: 48px; }
            .header h1 { font-size: 42px; font-weight: 800; color: white; margin-bottom: 12px; }
            .header p { font-size: 18px; color: rgba(255, 255, 255, 0.9); }
            
            .card { background: rgba(15, 32, 39, 0.85); backdrop-filter: blur(30px); border-radius: 24px; padding: 48px; border: 1px solid rgba(96, 165, 250, 0.3); }
            
            .form-section { margin-bottom: 32px; }
            .section-title { font-size: 20px; font-weight: 700; color: white; margin-bottom: 16px; }
            
            label { display: block; font-weight: 600; color: rgba(255, 255, 255, 0.9); margin-bottom: 8px; font-size: 14px; }
            
            input, select { width: 100%; padding: 14px; border: 2px solid rgba(96, 165, 250, 0.3); border-radius: 12px; font-size: 15px; background: rgba(255, 255, 255, 0.95); }
            
            .upload-box {
                background: rgba(255, 255, 255, 0.05);
                border: 2px dashed rgba(255, 255, 255, 0.3);
                border-radius: 12px;
                padding: 30px;
                text-align: center;
                cursor: pointer;
                transition: all 0.3s ease;
                margin-bottom: 20px;
            }
            
            .upload-box:hover {
                background: rgba(255, 255, 255, 0.1);
                border-color: rgba(255, 255, 255, 0.5);
                transform: translateY(-2px);
            }
            
            .upload-box.dragover {
                background: rgba(59, 130, 246, 0.2);
                border-color: #3b82f6;
            }
            
            .upload-icon { font-size: 48px; margin-bottom: 15px; }
            .upload-title { font-size: 18px; font-weight: 600; color: white; margin-bottom: 8px; }
            .upload-subtitle { font-size: 14px; color: rgba(255, 255, 255, 0.6); margin-bottom: 15px; }
            
            .file-list { margin-top: 15px; }
            .file-item {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 10px 15px;
                margin-top: 8px;
                display: flex;
                align-items: center;
                gap: 10px;
                font-size: 14px;
                color: white;
            }
            
            .measures-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin-top: 12px; }
            .measure-item { padding: 14px; background: rgba(15, 32, 39, 0.6); border: 2px solid rgba(96, 165, 250, 0.3); border-radius: 12px; display: flex; align-items: center; gap: 10px; }
            .measure-item.high-risk { border-color: rgba(239, 68, 68, 0.5); background: rgba(239, 68, 68, 0.1); }
            .measure-item label { margin: 0; cursor: pointer; color: white; }
            .risk-badge { background: #ef4444; color: white; padding: 2px 8px; border-radius: 8px; font-size: 11px; margin-left: auto; }
            
            .submit-btn { width: 100%; padding: 18px; background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%); color: white; border: none; border-radius: 14px; font-size: 17px; font-weight: 700; cursor: pointer; margin-top: 32px; }
            .submit-btn:hover { transform: translateY(-2px); }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>⚡ SF70 EEM Assessment Tool</h1>
                <p>PAS 2035:2023 Compliant Retrofit Assessment</p>
            </div>
            
            <div class="card">
                <form method="POST" enctype="multipart/form-data">
                    
                    <div class="form-section">
                        <div class="section-title">🏠 Property Details</div>
                        <div style="margin-bottom: 16px;">
                            <label>Property Address (Optional)</label>
                            <input type="text" name="address" placeholder="e.g., 14 Boreraig Place">
                        </div>
                        <div style="margin-bottom: 16px;">
                            <label>Build Year (Optional)</label>
                            <input type="text" name="build_year" placeholder="e.g., 1984">
                        </div>
                        <div>
                            <label>Document Provider</label>
                            <select name="provider">
                                <option value="pashub">PasHub</option>
                                <option value="elmhurst">Elmhurst</option>
                            </select>
                        </div>
                    </div>
                    
                    <div class="form-section">
                        <div class="section-title">📄 Upload Documents</div>
                        
                        <!-- Condition Report Upload -->
                        <div class="upload-box" id="conditionUpload">
                            <input type="file" id="conditionReport" name="pdfs" accept=".pdf" style="display:none;" multiple>
                            <div class="upload-icon">📄</div>
                            <div class="upload-title">Condition Report</div>
                            <div class="upload-subtitle">Click or drag PDF here</div>
                            <div id="conditionFileList" class="file-list"></div>
                        </div>
                        
                        <!-- Site Notes Upload -->
                        <div class="upload-box" id="siteNotesUpload">
                            <input type="file" id="siteNotes" name="pdfs" accept=".pdf" style="display:none;" multiple>
                            <div class="upload-icon">📋</div>
                            <div class="upload-title">Site Notes (Optional)</div>
                            <div class="upload-subtitle">Click or drag PDF here</div>
                            <div id="siteNotesFileList" class="file-list"></div>
                        </div>
                    </div>
                    
                    <div class="form-section">
                        <div class="section-title">🔧 Proposed Measures</div>
                        <div class="measures-grid">
                            <div class="measure-item high-risk">
                                <input type="checkbox" name="measure_ewi" id="ewi" value="1">
                                <label for="ewi">EWI</label>
                                <span class="risk-badge">HIGH RISK</span>
                            </div>
                            <div class="measure-item">
                                <input type="checkbox" name="measure_esh_hhr" id="esh" value="1">
                                <label for="esh">ESH HHR</label>
                            </div>
                            <div class="measure-item high-risk">
                                <input type="checkbox" name="measure_rir" id="rir" value="1">
                                <label for="rir">RIR</label>
                                <span class="risk-badge">HIGH RISK</span>
                            </div>
                            <div class="measure-item high-risk">
                                <input type="checkbox" name="measure_iwi" id="iwi" value="1">
                                <label for="iwi">IWI</label>
                                <span class="risk-badge">HIGH RISK</span>
                            </div>
                            <div class="measure-item">
                                <input type="checkbox" name="measure_loft" id="loft" value="1">
                                <label for="loft">Loft Insulation</label>
                            </div>
                            <div class="measure-item high-risk">
                                <input type="checkbox" name="measure_cwi" id="cwi" value="1">
                                <label for="cwi">CWI</label>
                                <span class="risk-badge">HIGH RISK</span>
                            </div>
                            <div class="measure-item">
                                <input type="checkbox" name="measure_controls" id="controls" value="1">
                                <label for="controls">Heating Controls</label>
                            </div>
                            <div class="measure-item">
                                <input type="checkbox" name="measure_boiler" id="boiler" value="1">
                                <label for="boiler">Boiler Upgrade</label>
                            </div>
                            <div class="measure-item">
                                <input type="checkbox" name="measure_ashp" id="ashp" value="1">
                                <label for="ashp">ASHP</label>
                            </div>
                            <div class="measure-item">
                                <input type="checkbox" name="measure_solar" id="solar" value="1">
                                <label for="solar">Solar PV</label>
                            </div>
                        </div>
                    </div>
                    
                    <button type="submit" class="submit-btn">📊 Generate SF70 Report</button>
                </form>
            </div>
        </div>
        
        <script>
            // Condition Report Upload - JavaScript with no f-string conflicts
            const conditionUpload = document.getElementById('conditionUpload');
            const conditionInput = document.getElementById('conditionReport');
            const conditionFileList = document.getElementById('conditionFileList');
            
            conditionUpload.addEventListener('click', function() {
                conditionInput.click();
            });
            
            conditionUpload.addEventListener('dragover', function(e) {
                e.preventDefault();
                conditionUpload.classList.add('dragover');
            });
            
            conditionUpload.addEventListener('dragleave', function() {
                conditionUpload.classList.remove('dragover');
            });
            
            conditionUpload.addEventListener('drop', function(e) {
                e.preventDefault();
                conditionUpload.classList.remove('dragover');
                conditionInput.files = e.dataTransfer.files;
                showConditionFiles();
            });
            
            conditionInput.addEventListener('change', showConditionFiles);
            
            function showConditionFiles() {
                conditionFileList.innerHTML = '';
                for (let i = 0; i < conditionInput.files.length; i++) {
                    const file = conditionInput.files[i];
                    const div = document.createElement('div');
                    div.className = 'file-item';
                    div.innerHTML = '<span>📄</span> <span style="flex:1;">' + file.name + '</span> <span>' + formatSize(file.size) + '</span>';
                    conditionFileList.appendChild(div);
                }
            }
            
            // Site Notes Upload
            const siteNotesUpload = document.getElementById('siteNotesUpload');
            const siteNotesInput = document.getElementById('siteNotes');
            const siteNotesFileList = document.getElementById('siteNotesFileList');
            
            siteNotesUpload.addEventListener('click', function() {
                siteNotesInput.click();
            });
            
            siteNotesUpload.addEventListener('dragover', function(e) {
                e.preventDefault();
                siteNotesUpload.classList.add('dragover');
            });
            
            siteNotesUpload.addEventListener('dragleave', function() {
                siteNotesUpload.classList.remove('dragover');
            });
            
            siteNotesUpload.addEventListener('drop', function(e) {
                e.preventDefault();
                siteNotesUpload.classList.remove('dragover');
                siteNotesInput.files = e.dataTransfer.files;
                showSiteNotesFiles();
            });
            
            siteNotesInput.addEventListener('change', showSiteNotesFiles);
            
            function showSiteNotesFiles() {
                siteNotesFileList.innerHTML = '';
                for (let i = 0; i < siteNotesInput.files.length; i++) {
                    const file = siteNotesInput.files[i];
                    const div = document.createElement('div');
                    div.className = 'file-item';
                    div.innerHTML = '<span>📋</span> <span style="flex:1;">' + file.name + '</span> <span>' + formatSize(file.size) + '</span>';
                    siteNotesFileList.appendChild(div);
                }
            }
            
            function formatSize(bytes) {
                if (bytes < 1024) return bytes + ' B';
                if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
                return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
            }
        </script>
    </body>
    </html>
    """
    
    return html


# ==================================================================================
# ROUTE HANDLER (UNCHANGED)
# ==================================================================================

async def sf70_tool_route(request: Request, user_row: dict):
    """Handle both GET and POST requests for SF70 tool"""
    
    if request.method == "GET":
        return HTMLResponse(content=get_sf70_html())
    
    # POST request - process form
    form = await request.form()
    
    # Get form data
    address = form.get("address", "")
    build_year = form.get("build_year", "")
    provider = form.get("provider", "pashub")
    
    # Get uploaded PDFs
    pdf_files = []
    for key in form.keys():
        if key == "pdfs":
            files = form.getlist("pdfs")
            pdf_files.extend(files)
    
    # Get selected measures
    proposed_measures = []
    measure_mapping = {
        "measure_ewi": "EWI",
        "measure_esh_hhr": "ESH HHR",
        "measure_rir": "RIR",
        "measure_iwi": "IWI",
        "measure_loft": "Loft Insulation",
        "measure_cwi": "CWI",
        "measure_controls": "Heating Controls",
        "measure_boiler": "Boiler Upgrade",
        "measure_ashp": "ASHP",
        "measure_solar": "Solar PV"
    }
    
    for form_key, measure_name in measure_mapping.items():
        if form.get(form_key):
            proposed_measures.append(measure_name)
    
    # Extract property data from PDFs
    if pdf_files:
        property_data = extract_property_data_from_pdfs(pdf_files, provider)
        
        # Override with manual inputs if provided
        if address:
            property_data["address"] = address
        if build_year:
            property_data["build_year"] = build_year
        
        # Detect existing measures
        existing_measures = detect_retrofit_measures(property_data)
        
        # Generate report
        pdf_bytes = generate_sf70_report(property_data, proposed_measures, existing_measures)
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=SF70_Report.pdf"}
        )
    
    # No files uploaded - show error
    return HTMLResponse(content=get_sf70_html(error="Please upload at least one PDF document"))