# main.py  — full app (drop-in replacement)

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, PlainTextResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response
from typing import List, Optional
from datetime import datetime, timedelta
import random
import io
import os
import json
import zipfile
from PIL import Image, ImageDraw, ImageFont

# ----------------------------
# App / middleware
# ----------------------------
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "dev-secret"))

DATA_DIR = "data"
CREDITS_FILE = os.path.join(DATA_DIR, "credits.json")
os.makedirs(DATA_DIR, exist_ok=True)

# ----------------------------
# Simple credit store (file-backed)
# ----------------------------
def _load_credits() -> int:
    if not os.path.exists(CREDITS_FILE):
        return 0
    try:
        with open(CREDITS_FILE, "r", encoding="utf-8") as f:
            return int(json.load(f).get("credits", 0))
    except Exception:
        return 0

def _save_credits(n: int) -> None:
    with open(CREDITS_FILE, "w", encoding="utf-8") as f:
        json.dump({"credits": int(n)}, f)

def get_credits() -> int:
    return _load_credits()

def add_credits(n: int) -> int:
    cur = _load_credits()
    cur += int(n)
    _save_credits(cur)
    return cur

def spend_credit() -> None:
    cur = _load_credits()
    if cur < 1:
        raise HTTPException(status_code=402, detail="Not enough credits. Please top up.")
    _save_credits(cur - 1)

# Seed credits once if env var set (handy for testing)
if get_credits() == 0 and os.getenv("INITIAL_CREDITS"):
    _save_credits(int(os.getenv("INITIAL_CREDITS")))

# ----------------------------
# Utilities
# ----------------------------
def _load_font(size: int = 30) -> ImageFont.FreeTypeFont:
    # Try a common font; fall back to PIL default
    for candidate in ["arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()

def _draw_text_with_outline(draw: ImageDraw.ImageDraw, xy, text, font):
    x, y = xy
    # black outline
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=font, fill="black")
    # white fill
    draw.text((x, y), text, font=font, fill="white")

def _stamp_image(binary: bytes, text: str, crop_bottom_px: int) -> bytes:
    with Image.open(io.BytesIO(binary)) as img:
        img = img.convert("RGB")  # Ensure RGB for JPEG save
        w, h = img.size
        crop_bottom_px = max(0, min(crop_bottom_px, h - 1))
        if crop_bottom_px:
            img = img.crop((0, 0, w, h - crop_bottom_px))

        draw = ImageDraw.Draw(img)
        font = _load_font(30)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = img.size[0] - tw - 12
        y = img.size[1] - th - 12
        _draw_text_with_outline(draw, (x, y), text, font)

        out = io.BytesIO()
        img.save(out, format="JPEG", quality=90, optimize=True)
        out.seek(0)
        return out.read()

def _parse_time_str(t: str) -> datetime:
    # Accept HH:MM or HH:MM:SS
    fmt = "%H:%M:%S" if t.count(":") == 2 else "%H:%M"
    return datetime.strptime(t, fmt)

# ----------------------------
# PAGES
# ----------------------------

BILLING_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Billing</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; line-height: 1.4; margin: 32px; }
    .btn { background:#6b46c1; color:white; padding:10px 14px; border:none; border-radius:10px; cursor:pointer; }
    .btn:disabled { opacity:.6; cursor:not-allowed; }
    .card { border:1px solid #eee; border-radius:12px; padding:16px; margin:12px 0; }
    .muted { color:#666; }
    .row { display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
    a.link { color:#6b46c1; text-decoration:none; }
  </style>
</head>
<body>
  <a class="link" href="/">Back</a>
  <h1>Billing</h1>
  <p>Credits: <strong>${credits}</strong> &middot; Price: £10/credit &middot; Minimum top-up: 5 credits (£50)</p>

  <div class="row">
    <button class="btn" onclick="alert('Top-up flow not wired yet. For testing, use the temporary Add Test Credits button below.')">Top up 5 credits (£50)</button>
    <a class="link" href="/tool">Open image timestamp tool →</a>
  </div>

  <div class="card">
    <h3>Temporary developer helpers</h3>
    <p class="muted">Only visible for now so you can test the tool. Remove before launch.</p>
    <div class="row">
      <button class="btn" onclick="add10()">Add Test Credits (+10)</button>
      <button class="btn" onclick="ping()">Ping Backend</button>
    </div>
  </div>

  <script>
    async function add10(){
      const r = await fetch('/debug/add_credits?n=10');
      const j = await r.json();
      alert('Credits now: '+j.credits);
      location.reload();
    }
    async function ping(){
      const r = await fetch('/api/ping');
      const j = await r.json();
      alert('Backend says ok='+j.ok+', message="'+j.message+'"');
    }
  </script>
</body>
</html>
"""

TOOL_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Image Timestamp Tool</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; line-height: 1.4; margin: 32px; }
    h1 { margin-bottom: 4px; }
    .muted { color:#666; }
    .grid { display:grid; gap:12px; max-width: 720px; }
    label { font-weight:600; }
    input, select { padding:10px; border:1px solid #ddd; border-radius:10px; width:100%; }
    .row { display:flex; gap:12px; }
    .btn { background:#0ea5e9; color:white; padding:12px 16px; border:none; border-radius:10px; cursor:pointer; }
    .btn.secondary { background:#6b46c1; }
    .card { border:1px solid #eee; border-radius:12px; padding:16px; margin-top:16px;}
    .badge { background:#f1f5f9; padding:4px 8px; border-radius:999px; }
  </style>
</head>
<body>
  <a href="/billing" style="text-decoration:none;color:#6b46c1;">← Back to billing</a>
  <h1>Image Timestamp Tool</h1>
  <p class="muted">Credits available: <strong>${credits}</strong> &nbsp; <span class="badge">1 credit per run</span></p>

  <form id="frm" class="grid" action="/api/process?download=1" method="post" enctype="multipart/form-data">
    <div>
      <label>Date to stamp</label>
      <input required name="date_to_use" placeholder="e.g. 30 May 2025" />
    </div>

    <div class="row">
      <div style="flex:1">
        <label>Mode</label>
        <select name="mode" id="mode">
          <option value="single">Single image</option>
          <option value="multiple">Multiple images (random times)</option>
        </select>
      </div>
      <div style="flex:1">
        <label>Crop from bottom (px)</label>
        <input required type="number" min="0" value="60" name="crop_bottom_px" />
      </div>
    </div>

    <div class="row">
      <div style="flex:1">
        <label>Start time</label>
        <input required type="time" step="1" value="13:00:00" name="start_time" id="start_time">
      </div>
      <div style="flex:1">
        <label>End time <span class="muted">(multiple mode)</span></label>
        <input type="time" step="1" value="15:00:00" name="end_time" id="end_time">
      </div>
    </div>

    <div>
      <label>Image(s)</label>
      <input required type="file" name="images" id="images" accept="image/*" multiple />
      <p class="muted">In <b>single</b> mode we use only the first file and stamp exactly the start time.  
      In <b>multiple</b> mode we stamp each file with a random time between start & end, then return a ZIP.</p>
    </div>

    <div class="row">
      <button class="btn" type="submit">Process (spends 1 credit)</button>
      <button class="btn secondary" type="button" onclick="testPing()">Ping backend</button>
    </div>
  </form>

  <div class="card">
    <h3>How it works</h3>
    <ul>
      <li>Crops X pixels from the bottom of each image.</li>
      <li>Stamps: <code>DATE, HH:MM:SS</code> bottom-right with white text + black outline.</li>
      <li>Returns a JPEG (single) or a ZIP (multiple).</li>
    </ul>
  </div>

  <script>
    const modeSel = document.getElementById('mode');
    const endTime = document.getElementById('end_time');
    function toggleEnd(){
      const m = modeSel.value;
      endTime.disabled = (m !== 'multiple');
      endTime.required = (m === 'multiple');
    }
    modeSel.addEventListener('change', toggleEnd);
    toggleEnd();

    async function testPing(){
      const r = await fetch('/api/ping');
      const j = await r.json();
      alert('ok='+j.ok+' message='+j.message);
    }
  </script>
</body>
</html>
"""

INDEX_HTML = """
<!doctype html>
<html><head><meta charset="utf-8"><title>Home</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif; margin:32px}
a.btn{display:inline-block;background:#0ea5e9;color:#fff;padding:12px 16px;border-radius:10px;text-decoration:none}
a.link{color:#6b46c1;text-decoration:none;margin-left:12px}
</style></head>
<body>
  <h1>Welcome</h1>
  <p>
    <a class="btn" href="/tool">Open image timestamp tool</a>
    <a class="link" href="/billing">Billing</a>
  </p>
</body></html>
"""

@app.get("/", response_class=HTMLResponse)
def home():
    return INDEX_HTML

@app.get("/billing", response_class=HTMLResponse)
def billing_page():
    from string import Template
    html = Template(BILLING_HTML).substitute(credits=get_credits())
    return HTMLResponse(html)

@app.get("/tool", response_class=HTMLResponse)
def tool_page():
    from string import Template
    html = Template(TOOL_HTML).substitute(credits=get_credits())
    return HTMLResponse(html)

# ----------------------------
# API
# ----------------------------

@app.get("/api/ping")
def ping():
    return {"ok": True, "message": "pong"}

@app.get("/debug/add_credits")
def debug_add_credits(n: int = 10):
    # TEMPORARY helper for testing during development
    return {"ok": True, "credits": add_credits(n)}

@app.post("/api/process")
async def process_images(
    request: Request,
    date_to_use: str = Form(...),
    mode: str = Form(...),  # "single" | "multiple"
    crop_bottom_px: int = Form(...),
    start_time: str = Form(...),
    end_time: Optional[str] = Form(None),
    images: List[UploadFile] = File(...)
):
    # Check credits (spend only on success)
    if get_credits() < 1:
        raise HTTPException(status_code=402, detail="Not enough credits. Please top up.")

    if not images:
        raise HTTPException(status_code=400, detail="Please upload at least one image.")

    # Parse times
    try:
        start_dt = _parse_time_str(start_time)
        end_dt = _parse_time_str(end_time) if end_time else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM or HH:MM:SS.")

    # Single-image mode
    if mode == "single":
        # use only the first image, stamp exactly start time
        file = images[0]
        binary = await file.read()
        stamp_text = f"{date_to_use}, {start_dt.strftime('%H:%M:%S')}"
        stamped = _stamp_image(binary, stamp_text, crop_bottom_px)

        # Spend credit on success
        spend_credit()

        headers = {"Content-Disposition": f'attachment; filename="{os.path.splitext(file.filename or "image")[0]}_stamped.jpg"'}
        return StreamingResponse(io.BytesIO(stamped), media_type="image/jpeg", headers=headers)

    # Multiple-images mode (random times between start & end)
    if mode == "multiple":
        if end_dt is None:
            raise HTTPException(status_code=400, detail="End time is required for multiple mode.")
        if end_dt <= start_dt:
            raise HTTPException(status_code=400, detail="End time must be after start time.")

        # Generate random times within the interval (unique-ish, then sorted)
        n = len(images)
        total_secs = (end_dt - start_dt).total_seconds()
        random_offsets = sorted(random.sample(range(int(total_secs)), k=min(n, int(total_secs)) )) \
                         if total_secs >= n else sorted([int(i*total_secs/n) for i in range(n)])
        # Ensure we have an offset per image
        while len(random_offsets) < n:
            random_offsets.append(random_offsets[-1] if random_offsets else 0)

        mem_zip = io.BytesIO()
        with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for idx, file in enumerate(images):
                binary = await file.read()
                ts = start_dt + timedelta(seconds=int(random_offsets[idx]))
                text = f"{date_to_use}, {ts.strftime('%H:%M:%S')}"
                stamped = _stamp_image(binary, text, crop_bottom_px)

                base = os.path.splitext(file.filename or f"image_{idx+1}.jpg")[0]
                zf.writestr(f"{base}_stamped.jpg", stamped)
        mem_zip.seek(0)

        # Spend credit on success
        spend_credit()

        headers = {"Content-Disposition": 'attachment; filename="stamped_images.zip"'}
        return StreamingResponse(mem_zip, media_type="application/zip", headers=headers)

    # Unknown mode
    raise HTTPException(status_code=400, detail="Mode must be 'single' or 'multiple'.")
