def parse_calculation_file(text: str, calc_type: str) -> Dict:
    """Parse calculation PDFs for ESSENTIAL info only - full PDFs will be attached to design"""
    data = {}
    
    if calc_type == "solar":
        # System size - match Easy PV format: "Installed capacity of PV system – kWp (stc): 3.690 kWp"
        size_patterns = [
            r'Installed capacity of PV system[^\d]*(\d+\.?\d*)\s*kWp',  # Easy PV format
            r'System size[:\s]+(\d+\.?\d*)\s*kW',
            r'Total.*?(\d+\.?\d*)\s*kWp'
        ]
        for pattern in size_patterns:
            size_match = re.search(pattern, text, re.IGNORECASE)
            if size_match:
                data['system_size'] = size_match.group(1)
                break
        
        # Extract panel info: "9 Anglo Solar solar panels"
        panel_patterns = [
            r'Input \d+:\s*(\d+)\s+([^,\n]+?)\s+solar panels',  # Easy PV: "Input 1: 9 Anglo Solar solar panels"
            r'(\d+)\s*x\s*([^\n]+?)\s+panels?',
            r'Panel.*?:\s*([^\n]+)'
        ]
        for pattern in panel_patterns:
            panel_match = re.search(pattern, text, re.IGNORECASE)
            if panel_match:
                if len(panel_match.groups()) == 2:
                    count, model = panel_match.groups()
                    data['panel_count'] = count
                    data['panel_model'] = model.strip()
                break
        
        # Extract inverter: "Growat MIN 3.6kW 1ph Hybrid"
        inverter_patterns = [
            r'(Growat[^\n]+)',
            r'(SolaX[^\n]+)',
            r'Inverter[^\n]*:\s*([^\n]+)',
            r'([\w\s]+\d+\.?\d*\s*kW[^\n]+inverter)'
        ]
        for pattern in inverter_patterns:
            inv_match = re.search(pattern, text, re.IGNORECASE)
            if inv_match:
                data['inverter_model'] = inv_match.group(1).strip()
                break
        
        # Create combined make/model description
        if 'panel_count' in data and 'panel_model' in data and 'inverter_model' in data:
            data['make_model'] = f"{data['panel_count']}x {data['panel_model']} with {data['inverter_model']}"
        elif 'panel_model' in data and 'inverter_model' in data:
            data['make_model'] = f"{data['panel_model']} with {data['inverter_model']}"
    
    elif calc_type == "heatpump":
        # Capacity
        capacity_match = re.search(r'(?:Capacity|Size|Output)[:\s]+(\d+\.?\d*)\s*kW', text, re.IGNORECASE)
