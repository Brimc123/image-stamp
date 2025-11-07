import io
import zipfile
from datetime import datetime, timedelta
from typing import List
from fastapi import UploadFile, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from PIL import Image, ImageDraw, ImageFont

from auth import require_active_user_row
from database import update_user_credits, add_transaction
from config import (
    TIMESTAMP_TOOL_COST,
    DEFAULT_FONT_SIZE,
    DEFAULT_CROP_HEIGHT,
    TIMESTAMP_PADDING,
    OUTLINE_WIDTH,
    FONT_PATHS,
)

# ============================================================================
# TIMESTAMP TOOL - FIXED VERSION v2
# Changes:
# 1. Reduced font scaling from 3.5% to 2.2% of image height
# 2. Minimal outline (1px) with softer dark grey color
# 3. Better auto-scaling for high-res images
# 4. Matches reference image styling
# ============================================================================

def _load_font(font_size: int) -> ImageFont.FreeTypeFont:
    last_err = None
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, font_size)
        except Exception as e:
            last_err = e
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        raise last_err or RuntimeError("Unable to load any font.")

def _draw_timestamp(img: Image.Image, text: str, font: ImageFont.FreeTypeFont) -> Image.Image:
    """
    Draws timestamp with minimal outline to match reference style.
    Uses 1px dark grey outline instead of thick black outline.
    """
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    x = img.width - text_w - TIMESTAMP_PADDING
    y = img.height - text_h - TIMESTAMP_PADDING

    # Draw minimal 1-pixel outline in dark grey (not pure black)
    # This creates subtle shadow effect like in reference image
    outline_color = (40, 40, 40)  # Dark grey instead of (0, 0, 0)
    
    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            if dx != 0 or dy != 0:  # Skip center (that's where white text goes)
                draw.text((x + dx, y + dy), text, font=font, fill=outline_color)

    # Draw main white text on top
    draw.text((x, y), text, font=font, fill=(255, 255, 255))
    return img

def process_timestamp_images(
    files: List[UploadFile],
    date_str: str,
    start_time_str: str,
    end_time_str: str,
    font_size: int,
    crop_height: int
) -> bytes:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    start_time = datetime.strptime(start_time_str, "%H:%M:%S").time()
    end_time = datetime.strptime(end_time_str, "%H:%M:%S").time()

    start_dt = datetime.combine(date_obj.date(), start_time)
    end_dt = datetime.combine(date_obj.date(), end_time)

    num_images = len(files)
    interval_seconds = 0 if num_images <= 1 else (end_dt - start_dt).total_seconds() / (num_images - 1)

    processed_images = []

    for idx, file in enumerate(files):
        current_dt = start_dt + timedelta(seconds=interval_seconds * idx)
        ts_text = current_dt.strftime("%d %b %Y, %H:%M:%S")

        img = Image.open(file.file).convert("RGB")
        
        # AUTO-SCALE font based on image height
        # Reduced from 3.5% to 2.2% for more reasonable sizing
        actual_font_size = font_size
        if font_size == 0 or font_size == DEFAULT_FONT_SIZE:
            # New formula: 2.2% of image height
            # 1080px -> 24pt, 1920px -> 42pt, 2160px -> 48pt
            actual_font_size = max(24, int(img.height * 0.022))
        
        font = _load_font(actual_font_size)

        # Crop from bottom BEFORE adding timestamp
        if crop_height and crop_height > 0:
            w, h = img.size
            img = img.crop((0, 0, w, max(1, h - crop_height)))

        img = _draw_timestamp(img, ts_text, font)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        buf.seek(0)
        processed_images.append((file.filename, buf.getvalue()))

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, data in processed_images:
            zf.writestr(f"stamped_{fname}", data)

    zip_buffer.seek(0)
    return zip_buffer.getvalue()

def get_timestamp_tool_page(request: Request):
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row

    try:
        has_access = user_row.get("timestamp_tool_access", 1) == 1
    except Exception:
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
        credits = float(user_row.get("credits", 0.0))
    except Exception:
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
        .form-group {{ margin-bottom: 25px; }}
        label {{
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 600;
        }}
        .help-text {{
            font-size: 13px;
            color: #666;
            margin-top: 5px;
            font-style: italic;
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
        .time-inputs select {{ padding: 12px; }}
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
        #fileInput {{ display: none; }}
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
        .submit-btn:hover {{ transform: scale(1.02); }}
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
        .warning-box {{
            background: #e3f2fd;
            border-left: 4px solid #2196f3;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 4px;
        }}
        .warning-box h4 {{
            color: #1976d2;
            margin-bottom: 8px;
        }}
        .warning-box ul {{
            margin-left: 20px;
            color: #555;
            line-height: 1.6;
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
        
        <div class="warning-box">
            <h4>⚙️ Recommended Settings:</h4>
            <ul>
                <li><strong>Font Size:</strong> Use <strong>0</strong> for automatic sizing (recommended), or 30-50 for manual control</li>
                <li><strong>Crop Height:</strong> Use <strong>500</strong> pixels to remove bottom timestamp bars from phone images</li>
                <li><strong>Auto-scale works best:</strong> Set font to 0 and let the tool calculate the right size</li>
            </ul>
        </div>
        
        <form method="POST" action="/tool/timestamp/process" enctype="multipart/form-data" id="timestampForm">
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
                        {''.join([f'<option value="{h:02d}" ' + ("selected" if h == 9 else "") + f'>{h:02d}</option>' for h in range(24)])}
                    </select>
                    <select name="start_minute" required>
                        <option value="">MM</option>
                        {''.join([f'<option value="{m:02d}" ' + ("selected" if m == 0 else "") + f'>{m:02d}</option>' for m in range(60)])}
                    </select>
                    <select name="start_second" required>
                        <option value="">SS</option>
                        {''.join([f'<option value="{s:02d}" ' + ("selected" if s == 0 else "") + f'>{s:02d}</option>' for s in range(60)])}
                    </select>
                </div>
            </div>
            
            <div class="form-group">
                <label>End Time</label>
                <div class="time-inputs">
                    <select name="end_hour" required>
                        <option value="">HH</option>
                        {''.join([f'<option value="{h:02d}" ' + ("selected" if h == 17 else "") + f'>{h:02d}</option>' for h in range(24)])}
                    </select>
                    <select name="end_minute" required>
                        <option value="">MM</option>
                        {''.join([f'<option value="{m:02d}" ' + ("selected" if m == 0 else "") + f'>{m:02d}</option>' for m in range(60)])}
                    </select>
                    <select name="end_second" required>
                        <option value="">SS</option>
                        {''.join([f'<option value="{s:02d}" ' + ("selected" if s == 0 else "") + f'>{s:02d}</option>' for s in range(60)])}
                    </select>
                </div>
            </div>
            
            <div class="form-group">
                <label>Font Size (pt)</label>
                <input type="number" name="font_size" value="0" min="0" max="150" required>
                <div class="help-text">Set to 0 for automatic sizing (recommended), or use 30-50 for manual sizing</div>
            </div>
            
            <div class="form-group">
                <label>Crop from Bottom (pixels)</label>
                <input type="number" name="crop_height" value="500" min="0" max="1000" required>
                <div class="help-text">Removes bottom info bar. Use 500 for phone images, 0 for no cropping</div>
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
                fileInfo.textContent = '✅ ' + files.length + ' file(s) selected: ' + fileNames;
                fileInfo.style.display = 'block';
            }}
        }}
    </script>
</body>
</html>
    """
    return HTMLResponse(html_content)

async def post_timestamp_tool(request: Request, user_row: dict):
    try:
        has_access = user_row.get("timestamp_tool_access", 1) == 1
    except Exception:
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
        credits = float(user_row.get("credits", 0.0))
    except Exception:
        credits = 0.0

    # Check if user is admin (admin gets free usage)
    from database import is_admin, log_usage
    is_admin_user = is_admin(user_row["id"])

    if not is_admin_user and credits < TIMESTAMP_TOOL_COST:

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

    form = await request.form()
    files = form.getlist("files")
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

    date_str = form.get("date")
    start_hour = form.get("start_hour")
    start_minute = form.get("start_minute")
    start_second = form.get("start_second")
    end_hour = form.get("end_hour")
    end_minute = form.get("end_minute")
    end_second = form.get("end_second")
    try:
        font_size = int(form.get("font_size", DEFAULT_FONT_SIZE))
    except Exception:
        font_size = DEFAULT_FONT_SIZE
    try:
        crop_height = int(form.get("crop_height", DEFAULT_CROP_HEIGHT))
    except Exception:
        crop_height = DEFAULT_CROP_HEIGHT

    start_time_str = f"{start_hour}:{start_minute}:{start_second}"
    end_time_str = f"{end_hour}:{end_minute}:{end_second}"

    try:
        zip_data = process_timestamp_images(
            files, date_str, start_time_str, end_time_str, font_size, crop_height
        )
    except Exception as e:
        return HTMLResponse(f"""
            <!DOCTYPE html>
            <html>
            <head><title>Processing Error</title></head>
            <body>
                <h1>Processing Error</h1>
                <p>Error: {str(e)}</p>
                <a href="/tool/timestamp">Try Again</a>
            </body>
            </html>
        """)

    try:
        user_id = user_row["id"]
        
        # Deduct credits only if not admin
        if not is_admin_user:
            new_balance = credits - TIMESTAMP_TOOL_COST
            update_user_credits(user_id, new_balance)
            add_transaction(user_id, -TIMESTAMP_TOOL_COST, "timestamp")
            log_usage(user_id, "Timestamp Tool", TIMESTAMP_TOOL_COST, f"Processed {len(files)} images")
        else:
            # Admin usage - free but still logged
            log_usage(user_id, "Timestamp Tool", 0.00, f"Admin - Processed {len(files)} images")
    except Exception as e:
        print(f"Error updating credits/logging: {e}")

    return Response(
        content=zip_data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=timestamped_images_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        }
    )
