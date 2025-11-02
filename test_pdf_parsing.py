import pdfplumber
import re

# Test parsing the Condition Report
pdf_path = input("Enter the full path to your Condition Report PDF: ")

print("\n" + "="*80)
print("PDF PARSING DEBUG TOOL")
print("="*80 + "\n")

try:
    with pdfplumber.open(pdf_path) as pdf:
        print(f"📄 Total pages: {len(pdf.pages)}\n")
        
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            print(f"\n{'='*80}")
            print(f"PAGE {page_num}")
            print('='*80)
            print(text)
            print('\n')
            
            # Try to find background ventilation patterns
            bg_patterns = [
                r'Background\s+Ventilation\s+Area\s*\(mm2?\)\s*(\d+)',
                r'Trickle\s+[Vv]ent.*?(\d+)\s*mm',
                r'Background\s+Ventilat.*?(\d+)\s*mm'
            ]
            
            print(f"\n🔍 SEARCHING FOR VENTILATION DATA ON PAGE {page_num}:")
            for pattern in bg_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    print(f"   ✅ Found: {match.group(0)} → Value: {match.group(1)}")
            
            # Check for fans
            if re.search(r'fan', text, re.IGNORECASE):
                print(f"   ✅ Found 'fan' mentioned on this page")
                fan_context = re.findall(r'.{0,50}fan.{0,50}', text, re.IGNORECASE)
                for context in fan_context[:3]:  # Show first 3 matches
                    print(f"      Context: {context.strip()}")
            
            print()

except FileNotFoundError:
    print("❌ File not found! Please check the path.")
except Exception as e:
    print(f"❌ Error: {e}")

print("\n" + "="*80)
print("DEBUG COMPLETE")
print("="*80)