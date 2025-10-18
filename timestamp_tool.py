import io
import os
import zipfile
from datetime import datetime, timedelta
from typing import List
from fastapi import UploadFile, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from PIL import Image, ImageDraw, ImageFont
from auth import require_active_user_row
from database import update_user_credits, add_transaction
from config import TIMESTAMP_TOOL_COST, DEFAULT_FONT_SIZE, TIMESTAMP_PADDING, OUTLINE_WIDTH, FONT_PATHS

def get_timestamp_tool_page(request: Request):
    """Timestamp tool page"""
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
            <head>
                <title>Access Denied</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .container {
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 10px 25px rgba(0,0,0,0.2);
                        text-align: center;
                        max-width: 400px;
                    }
                    h1 { color: #e74c3c; margin-bottom: 20px; }
                    p { color: #555; margin-bottom: 30px; }
                    a {
                        display: inline-block;
                        padding: 12px 30px;
                        background: #667eea;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        transition: background 0.3s;
                    }
                    a:hover { background: #764ba2; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Access Denied</h1>
                    <p>Your access to the Timestamp Tool has been suspended. Please contact the administrator.</p>
                    <a href="/">Back to Dashboard</a>
                </div>
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
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }}
        .header h1 {{
            color: #333;
            font-size: 28px;
        }}
        .credits {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 10px 20px;
            border-radius: 25px;
            font-weight: 600;
            font-size: 24pt;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
            max-width: 800px;
            margin: 0 auto;
        }}
        h2 {{
            color: #333;
            margin-bottom: 20px;
        }}
        .form-group {{
            margin-bottom: 25px;
        }}
        label {{
            display: block;
            margin-bottom: 10px;
            color: #555;
            font-weight: 600;
        }}
        input[type="file"],
        input[type="text"],
        input[type="number"] {{
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
        }}
        input:focus {{
            outline: none;
            border-color: #667eea;
        }}
        button {{
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }}
        button:hover {{
            transform: translateY(-2px);
        }}
        button:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}
        .back-btn {{
            display: inline-block;
            padding: 12px 30px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            margin-top: 20px;
        }}
        .back-btn:hover {{
            background: #764ba2;
        }}
        .info-box {{
            background: #e8f4f8;
            border-left: 4px solid #2196F3;
            padding: 15px;
            margin-bottom: 25px;
            border-radius: 5px;
        }}
        .info-box p {{
            color: #555;
            margin: 5px 0;
        }}
        #status {{
            margin-top: 20px;
            padding: 15px;
            border-radius: 8px;
            display: none;
        }}
        .success {{
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }}
        .error {{
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }}
        .processing {{
            background: #fff3cd;
            color: #856404;
            border: 1px solid #ffeaa7;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Timestamp Tool</h1>
        <div class="credits">£{credits:.2f}</div>
    </div>

    <div class="container">
        <div class="info-box">
            <p><strong>Cost:</strong> £{TIMESTAMP_TOOL_COST:.2f} per batch</p>
            <p><strong>Your Credits:</strong> £{credits:.2f}</p>
            <p><strong>How it works:</strong> Upload multiple images, set date & time range, and download timestamped images as ZIP</p>
        </div>

        <form id="stampForm" enctype="multipart/form-data">
            <div class="form-group">
                <label>Upload Images (multiple)</label>
                <input type="file" name="files" id="files" multiple accept="image/*" required>
            </div>

            <div class="form-group">
                <label>Date (e.g., 30 May 2025)</label>
                <input type="text" name="date_text" id="date_text" placeholder="30 May 2025" required>
            </div>

            <div class="form-group">
                <label>Start Time (HH:MM:SS)</label>
                <input type="text" name="start_time" id="start_time" placeholder="13:00:00" required>
            </div>

            <div class="form-group">
                <label>End Time (HH:MM:SS)</label>
                <input type="text" name="end_time" id="end_time" placeholder="15:00:00" required>
            </div>

            <div class="form-group">
                <label>Font Size (default: {DEFAULT_FONT_SIZE})</label>
                <input type="number" name="font_size" id="font_size" value="{DEFAULT_FONT_SIZE}" min="20" max="120" required>
            </div>

            <div class="form-group">
                <label>Crop Height from Bottom (pixels)</label>
                <input type="number" name="crop_height" id="crop_height" value="0" min="0" required>
            </div>

            <button type="submit" id="submitBtn">Process Images</button>
        </form>

        <div id="status"></div>

        <a href="/" class="back-btn">Back to Dashboard</a>
    </div>

    <script>
        document.getElementById('stampForm').addEventListener('submit', async (e) => {{
            e.preventDefault();
            
            const statusDiv = document.getElementById('status');
            const submitBtn = document.getElementById('submitBtn');
            
            statusDiv.style.display = 'block';
            statusDiv.className = 'processing';
            statusDiv.textContent = 'Processing images... Please wait.';
            submitBtn.disabled = true;
            
            const formData = new FormData();
            const files = document.getElementById('files').files;
            
            for (let i = 0; i < files.length; i++) {{
                formData.append('files', files[i]);
            }}
            
            formData.append('date_text', document.getElementById('date_text').value);
            formData.append('start_time', document.getElementById('start_time').value);
            formData.append('end_time', document.getElementById('end_time').value);
            formData.append('font_size', document.getElementById('font_size').value);
            formData.append('crop_height', document.getElementById('crop_height').value);
            
            try {{
                const response = await fetch('/api/process-timestamp', {{
                    method: 'POST',
                    body: formData
                }});
                
                if (response.ok) {{
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'timestamped_images.zip';
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    
                    statusDiv.className = 'success';
                    statusDiv.textContent = 'Success! Your images have been downloaded. £{TIMESTAMP_TOOL_COST:.2f} has been deducted from your credits.';
                    
                    // Reload page after 2 seconds to update credits
                    setTimeout(() => {{
                        window.location.reload();
                    }}, 2000);
                }} else {{
                    const error = await response.text();
                    statusDiv.className = 'error';
                    statusDiv.textContent = error || 'Error processing images';
                    submitBtn.disabled = false;
                }}
            }} catch (error) {{
                statusDiv.className = 'error';
                statusDiv.textContent = 'Network error: ' + error.message;
                submitBtn.disabled = false;
            }}
        }});
    </script>
</body>
</html>
    """
    return HTMLResponse(html_content)

async def process_timestamp_images(
    request: Request,
    files: List[UploadFile],
    date_text: str,
    start_time: str,
    end_time: str,
    font_size: int,
    crop_height: int
):
    """Process images with timestamps"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return Response(content="Unauthorized", status_code=401)
    
    # Check credits
    try:
        current_credits = user_row["credits"]
    except (KeyError, TypeError):
        current_credits = 0.0
    
    if current_credits < TIMESTAMP_TOOL_COST:
        return Response(content="Insufficient credits. Please top up.", status_code=400)
    
    # Check minimum images
    if len(files) < 2:
        return Response(content="Please upload at least 2 images.", status_code=400)
    
    user_id = user_row["id"]
    
    try:
        # Parse times
        start_dt = datetime.strptime(start_time, "%H:%M:%S")
        end_dt = datetime.strptime(end_time, "%H:%M:%S")
        
        if start_dt >= end_dt:
            return Response(content="Start time must be before end time", status_code=400)
        
        # Calculate time distribution
        total_images = len(files)
        total_duration = (end_dt - start_dt).total_seconds()
        interval = total_duration / (total_images - 1)
        
        # Load font
        font = None
        for font_path in FONT_PATHS:
            try:
                font = ImageFont.truetype(font_path, font_size)
                break
            except:
                continue
        
        if font is None:
            font = ImageFont.load_default()
        
        # Create ZIP file
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for idx, file in enumerate(files):
                # Calculate timestamp for this image
                timestamp_dt = start_dt + timedelta(seconds=interval * idx)
                time_str = timestamp_dt.strftime("%H:%M:%S")
                full_timestamp = f"{date_text}, {time_str}"
                
                # Read and process image
                image_data = await file.read()
                img = Image.open(io.BytesIO(image_data))
                
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                width, height = img.size
                
                # Crop from bottom if specified
                if crop_height > 0 and crop_height < height:
                    img = img.crop((0, 0, width, height - crop_height))
                
                # Add timestamp
                draw = ImageDraw.Draw(img)
                
                # Get text size
                bbox = draw.textbbox((0, 0), full_timestamp, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                
                # Position at bottom right with padding
                x = img.size[0] - text_width - TIMESTAMP_PADDING
                y = img.size[1] - text_height - TIMESTAMP_PADDING
                
                # Draw black outline (3px thick)
                for adj_x in range(-OUTLINE_WIDTH, OUTLINE_WIDTH + 1):
                    for adj_y in range(-OUTLINE_WIDTH, OUTLINE_WIDTH + 1):
                        if adj_x != 0 or adj_y != 0:
                            draw.text((x + adj_x, y + adj_y), full_timestamp, font=font, fill=(0, 0, 0))
                
                # Draw white text on top
                draw.text((x, y), full_timestamp, font=font, fill=(255, 255, 255))
                
                # Save to ZIP
                output = io.BytesIO()
                img.save(output, format='JPEG', quality=95)
                output.seek(0)
                
                original_filename = file.filename or f"image_{idx}.jpg"
                name, ext = os.path.splitext(original_filename)
                new_filename = f"{name}_stamped{ext}"
                
                zip_file.writestr(new_filename, output.read())
        
        # Deduct credits
        new_credits = current_credits - TIMESTAMP_TOOL_COST
        update_user_credits(user_id, new_credits)
        add_transaction(user_id, -TIMESTAMP_TOOL_COST, "processing")
        
        # Return ZIP file
        zip_buffer.seek(0)
        return Response(
            content=zip_buffer.read(),
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=timestamped_images.zip"}
        )
    
    except Exception as e:
        # Refund on error
        return Response(content=f"Error processing images: {str(e)}", status_code=500)
