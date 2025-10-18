import io
import os
import zipfile
from datetime import datetime, timedelta
from typing import List
from fastapi import UploadFile, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from PIL import Image, ImageDraw, ImageFont
from auth import require_active_user_row
from database import get_db, update_user_credits, add_transaction
from config import TIMESTAMP_TOOL_COST


def process_timestamp_images(
    files: List[UploadFile],
    date_str: str,
    start_time_str: str,
    end_time_str: str,
    font_size: int,
    crop_height: int
) -> bytes:
    """Process images with timestamps"""
    
    # Parse date (format: YYYY-MM-DD from date input)
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    
    # Parse times
    start_time = datetime.strptime(start_time_str, "%H:%M:%S").time()
    end_time = datetime.strptime(end_time_str, "%H:%M:%S").time()
    
    # Combine date with times
    start_datetime = datetime.combine(date_obj.date(), start_time)
    end_datetime = datetime.combine(date_obj.date(), end_time)
    
    # Calculate time interval
    num_images = len(files)
    if num_images > 1:
        total_seconds = (end_datetime - start_datetime).total_seconds()
        interval_seconds = total_seconds / (num_images - 1)
    else:
        interval_seconds = 0
    
    # Font setup
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    text_color = (220, 220, 220)  # Off-white/light gray (not bright white)
    outline_color = (0, 0, 0)  # Black
    outline_width = 2
    
    # Process each image
    processed_images = []
    
    for idx, file in enumerate(files):
        # Calculate timestamp for this image
        current_datetime = start_datetime + timedelta(seconds=interval_seconds * idx)
        
        # Format: "DD MMM YYYY, HH:MM:SS" (e.g., "03 Apr 2025, 14:34:22")
        timestamp_text = current_datetime.strftime("%d %b %Y, %H:%M:%S")
        
        # Open image
        img = Image.open(file.file).convert("RGB")
        
        # Crop from bottom if specified
        if crop_height > 0:
            width, height = img.size
            img = img.crop((0, 0, width, height - crop_height))
        
        # Draw timestamp
        draw = ImageDraw.Draw(img)
        
        # Get text size
        bbox = draw.textbbox((0, 0), timestamp_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # Position: bottom right with padding
        padding = 30
        x = img.width - text_width - padding
        y = img.height - text_height - padding
        
        # Draw outline (black)
        for adj_x in range(-outline_width, outline_width + 1):
            for adj_y in range(-outline_width, outline_width + 1):
                draw.text((x + adj_x, y + adj_y), timestamp_text, font=font, fill=outline_color)
        
        # Draw main text (off-white)
        draw.text((x, y), timestamp_text, font=font, fill=text_color)
        
        # Save to memory
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="JPEG", quality=95)
        img_bytes.seek(0)
        
        processed_images.append({
            "filename": file.filename,
            "data": img_bytes.getvalue()
        })
    
    # Create ZIP file
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for img_data in processed_images:
            zip_file.writestr(f"stamped_{img_data['filename']}", img_data["data"])
    
    zip_buffer.seek(0)
    return zip_buffer.getvalue()


def get_timestamp_tool_page(request: Request):
    """Display timestamp tool page"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    # Check tool access
    try:
        has_access = user_row["timestamp_tool_access"] == 1
    except (KeyError, TypeError):
        has_access = True
    
    if not has_access:
        return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head><title>Access Denied</title></head>
            <body>
                <h1>Access Denied</h1>
                <p>Your access to the Timestamp Tool has been suspended.</p>
                <a href="/">Back to Dashboard</a>
            </body>
            </html>
        """)
    
    try:
        credits = user_row["credits"]
    except (KeyError, TypeError):
        credits = 0.0
    
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Timestamp Tool - AutoDate</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .header {{
            background: white;
            padding: 20px 40px;
            border-radius: 15px;
            margin-bottom: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }}
        .header h1 {{
            color: #333;
            font-size: 32px;
        }}
        .credits {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 10px 20px;
            border-radius: 25px;
            font-weight: 600;
            font-size: 18px;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }}
        .form-group {{
            margin-bottom: 25px;
        }}
        label {{
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 600;
        }}
        input[type="date"],
        input[type="number"],
        select {{
            width: 100%;
            padding: 12px;
            border: 2px solid #ddd;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s;
        }}
        input:focus, select:focus {{
            outline: none;
            border-color: #667eea;
        }}
        .time-inputs {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
        }}
        .time-inputs select {{
            padding: 12px;
        }}
        .dropzone {{
            border: 3px dashed #667eea;
            border-radius: 15px;
            padding: 40px;
            text-align: center;
            background: #f8f9ff;
            cursor: pointer;
            transition: all 0.3s;
            margin-bottom: 20px;
        }}
        .dropzone:hover {{
            background: #e8ebff;
            border-color: #764ba2;
        }}
        .dropzone.dragover {{
            background: #d8e0ff;
            border-color: #764ba2;
        }}
        #fileInput {{
            display: none;
        }}
        .file-info {{
            margin-top: 15px;
            padding: 15px;
            background: #e8f5e9;
            border-radius: 8px;
            color: #2e7d32;
            font-weight: 600;
        }}
        .submit-btn {{
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }}
        .submit-btn:hover {{
            transform: scale(1.02);
        }}
        .back-link {{
            display: inline-block;
            margin-top: 20px;
            color: #667eea;
            text-decoration: none;
            font-weight: 600;
        }}
        .cost-info {{
            background: #fff3cd;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            color: #856404;
            font-weight: 600;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Timestamp Tool</h1>
        <div class="credits">£{credits:.2f}</div>
    </div>
    
    <div class="container">
        <div class="cost-info">
            💰 Cost: £{TIMESTAMP_TOOL_COST:.2f} per batch
        </div>
        
        <form method="POST" enctype="multipart/form-data" id="timestampForm">
            <div class="form-group">
                <label>Upload Images</label>
                <div class="dropzone" id="dropzone">
                    <p style="font-size: 18px; color: #667eea;">📁 Click or drag images here</p>
                    <p style="font-size: 14px; color: #999; margin-top: 10px;">Select multiple images</p>
                </div>
                <input type="file" name="files" id="fileInput" multiple accept="image/*">
                <div id="fileInfo" class="file-info" style="display: none;"></div>
            </div>
            
            <div class="form-group">
                <label>Date</label>
                <input type="date" name="date" required>
            </div>
            
            <div class="form-group">
                <label>Start Time</label>
                <div class="time-inputs">
                    <select name="start_hour" required>
                        <option value="">HH</option>
                        {' '.join([f'<option value="{h:02d}" {"selected" if h == 9 else ""}>{h:02d}</option>' for h in range(24)])}
                    </select>
                    <select name="start_minute" required>
                        <option value="">MM</option>
                        {' '.join([f'<option value="{m:02d}" {"selected" if m == 0 else ""}>{m:02d}</option>' for m in range(60)])}
                    </select>
                    <select name="start_second" required>
                        <option value="">SS</option>
                        {' '.join([f'<option value="{s:02d}" {"selected" if s == 0 else ""}>{s:02d}</option>' for s in range(60)])}
                    </select>
                </div>
            </div>
            
            <div class="form-group">
                <label>End Time</label>
                <div class="time-inputs">
                    <select name="end_hour" required>
                        <option value="">HH</option>
                        {' '.join([f'<option value="{h:02d}" {"selected" if h == 17 else ""}>{h:02d}</option>' for h in range(24)])}
                    </select>
                    <select name="end_minute" required>
                        <option value="">MM</option>
                        {' '.join([f'<option value="{m:02d}" {"selected" if m == 0 else ""}>{m:02d}</option>' for m in range(60)])}
                    </select>
                    <select name="end_second" required>
                        <option value="">SS</option>
                        {' '.join([f'<option value="{s:02d}" {"selected" if s == 0 else ""}>{s:02d}</option>' for s in range(60)])}
                    </select>
                </div>
            </div>
            
            <div class="form-group">
                <label>Font Size (pt)</label>
                <input type="number" name="font_size" value="25" min="10" max="100" required>
            </div>
            
            <div class="form-group">
                <label>Crop from Bottom (pixels)</label>
                <input type="number" name="crop_height" value="60" min="0" max="500" required>
            </div>
            
            <button type="submit" class="submit-btn">Process Images</button>
        </form>
        
        <a href="/" class="back-link">← Back to Dashboard</a>
    </div>
    
    <script>
        const dropzone = document.getElementById('dropzone');
        const fileInput = document.getElementById('fileInput');
        const fileInfo = document.getElementById('fileInfo');
        
        dropzone.addEventListener('click', () => fileInput.click());
        
        dropzone.addEventListener('dragover', (e) => {{
            e.preventDefault();
            dropzone.classList.add('dragover');
        }});
        
        dropzone.addEventListener('dragleave', () => {{
            dropzone.classList.remove('dragover');
        }});
        
        dropzone.addEventListener('drop', (e) => {{
            e.preventDefault();
            dropzone.classList.remove('dragover');
            fileInput.files = e.dataTransfer.files;
            updateFileInfo();
        }});
        
        fileInput.addEventListener('change', updateFileInfo);
        
        function updateFileInfo() {{
            const files = fileInput.files;
            if (files.length > 0) {{
                const fileNames = Array.from(files).map(f => f.name).join(', ');
                fileInfo.textContent = `✅ ${{files.length}} file(s) selected: ${{fileNames}}`;
                fileInfo.style.display = 'block';
            }}
        }}
    </script>
</body>
</html>
    """
    return HTMLResponse(html_content)


async def post_timestamp_tool(request: Request):
    """Process timestamp tool submission"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    # Check tool access
    try:
        has_access = user_row["timestamp_tool_access"] == 1
    except (KeyError, TypeError):
        has_access = True
    
    if not has_access:
        return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head><title>Access Denied</title></head>
            <body>
                <h1>Access Denied</h1>
                <p>Your access to the Timestamp Tool has been suspended.</p>
                <a href="/">Back to Dashboard</a>
            </body>
            </html>
        """)
    
    # Check credits
    try:
        credits = user_row["credits"]
    except (KeyError, TypeError):
        credits = 0.0
    
    if credits < TIMESTAMP_TOOL_COST:
        return HTMLResponse(f"""
            <!DOCTYPE html>
            <html>
            <head><title>Insufficient Credits</title></head>
            <body>
                <h1>Insufficient Credits</h1>
                <p>You need £{TIMESTAMP_TOOL_COST:.2f} to use this tool.</p>
                <p>Your current balance: £{credits:.2f}</p>
                <a href="/billing">Top Up Credits</a> | <a href="/">Back to Dashboard</a>
            </body>
            </html>
        """)
    
    # Parse form data
    form_data = await request.form()
    
    files = form_data.getlist("files")
    if not files:
        return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head><title>Error</title></head>
            <body>
                <h1>Error</h1>
                <p>No files uploaded.</p>
                <a href="/tool/timestamp">Try Again</a>
            </body>
            </html>
        """)
    
    # Get form values
    date_str = form_data.get("date")
    start_hour = form_data.get("start_hour")
    start_minute = form_data.get("start_minute")
    start_second = form_data.get("start_second")
    end_hour = form_data.get("end_hour")
    end_minute = form_data.get("end_minute")
    end_second = form_data.get("end_second")
    font_size = int(form_data.get("font_size", 25))
    crop_height = int(form_data.get("crop_height", 60))
    
    # Combine time components
    start_time_str = f"{start_hour}:{start_minute}:{start_second}"
    end_time_str = f"{end_hour}:{end_minute}:{end_second}"
    
    # Process images
    try:
        zip_data = process_timestamp_images(
            files, date_str, start_time_str, end_time_str, font_size, crop_height
        )
    except Exception as e:
        return HTMLResponse(f"""
            <!DOCTYPE html>
            <html>
            <head><title>Error</title></head>
            <body>
                <h1>Processing Error</h1>
                <p>Error: {str(e)}</p>
                <a href="/tool/timestamp">Try Again</a>
            </body>
            </html>
        """)
    
    # Deduct credits
    user_id = user_row["id"]
    email = user_row["email"]
    new_balance = credits - TIMESTAMP_TOOL_COST
    
    update_user_credits(user_id, new_balance)
    add_transaction(
        user_id,
        -TIMESTAMP_TOOL_COST,
        "Timestamp Tool Usage",
        f"Processed {len(files)} images"
    )
    
    # Return ZIP file
    return Response(
        content=zip_data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=timestamped_images_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        }
    )
