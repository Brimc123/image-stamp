# main.py
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageOps

app = FastAPI()

# ----------------------- health/ping -----------------------
@app.get("/health")
def health() -> PlainTextResponse:
    return PlainTextResponse("ok")

@app.get("/api/ping")
async def api_ping() -> JSONResponse:
    return JSONResponse({"ok": True, "message": "pong"})

# ----------------------- font helper -----------------------
def _load_font(px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """
    Try to load a nice TTF font (DejaVuSans). If not available, fall back to the
    default Pillow bitmap font so we never crash on Render.
    """
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, px)
        except Exception:
            pass
    return ImageFont.load_default()

# ----------------------- stamping core -----------------------
def apply_stamp(
    base_im: Image.Image,
    text: str,
    position: str = "center",
    size_px: int = 48,
    opacity_pct: int = 60,
    margin_px: int = 24,
) -> Image.Image:
    """
    Draw a semi-transparent text watermark on the image.
    """
    # normalize orientation and ensure RGBA
    im = ImageOps.exif_transpose(base_im).convert("RGBA")

    # draw onto transparent overlay, then alpha-compose
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font = _load_font(size_px)
    # measure text
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=2)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # choose position
    W, H = im.size
    x, y = {
        "top-left":      (margin_px, margin_px),
        "top-right":     (W - text_w - margin_px, margin_px),
        "bottom-left":   (margin_px, H - text_h - margin_px),
        "bottom-right":  (W - text_w - margin_px, H - text_h - margin_px),
        "center":        ((W - text_w) // 2, (H - text_h) // 2),
    }.get(position, ((W - text_w) // 2, (H - text_h) // 2))

    # opacity and colors
    a = max(0, min(100, opacity_pct)) * 255 // 100
    fill = (255, 255, 255, a)       # white text
    stroke = (0, 0, 0, int(a * 0.9)) # dark outline for contrast

    # draw text with thin stroke for readability
    draw.text((x, y), text, font=font, fill=fill, stroke_width=2, stroke_fill=stroke)

    # combine
    out = Image.alpha_composite(im, overlay)

    # return in original mode if possible
    if base_im.mode != "RGBA":
        out = out.convert(base_im.mode)
    return out

# ----------------------- Image Stamp API -----------------------
@app.post("/api/stamp")
async def api_stamp(
    file: UploadFile = File(...),
    text: str = Form("Autodate"),
    position: str = Form("center"),
    size: int = Form(48),
    opacity: int = Form(60),
):
    # read upload into PIL
    data = await file.read()
    try:
        im = Image.open(BytesIO(data))
    except Exception:
        return JSONResponse({"ok": False, "error": "Unsupported image"}, status_code=400)

    stamped = apply_stamp(im, text=text.strip() or "Autodate",
                          position=position, size_px=int(size), opacity_pct=int(opacity))

    # stream PNG back
    buf = BytesIO()
    stamped.save(buf, format="PNG")
    buf.seek(0)
    headers = {"Content-Disposition": 'inline; filename="stamped.png"'}
    return StreamingResponse(buf, media_type="image/png", headers=headers)

# ----------------------- Tester UI (/) -----------------------
INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Image Stamp · Autodate</title>
  <style>
    :root{
      --bg:#f6f7fb; --card:#ffffff; --text:#111827; --muted:#6b7280; --border:#e5e7eb;
      --accent:#4f46e5; --accent2:#3730a3; --shadow:0 10px 20px rgba(0,0,0,.07);
      --radius:16px;
    }
    @media (prefers-color-scheme: dark){
      :root{ --bg:#0f1221; --card:#12162b; --text:#e5e7eb; --muted:#9ca3af; --border:#232743; --shadow:0 12px 26px rgba(0,0,0,.35); }
    }
    *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--text);
      font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;}
    .container{max-width:1000px;margin:30px auto;padding:0 18px}
    .card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow);padding:18px}
    h1{margin:0 0 10px 0;font-size:22px}
    .row{display:grid;grid-template-columns:1fr;gap:18px}
    @media(min-width:900px){ .row{grid-template-columns: 1fr 1fr} }
    label{display:block;font-weight:600;margin-top:10px}
    input[type="text"],select,input[type="number"],input[type="range"]{
      width:100%;padding:10px;border-radius:12px;border:1px solid var(--border);background:transparent;color:var(--text)
    }
    input[type="file"]{width:100%}
    .btn{margin-top:12px;background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;border:0;border-radius:12px;padding:12px 16px;cursor:pointer;font-weight:700;box-shadow:0 10px 18px rgba(79,70,229,.35)}
    .btn:disabled{opacity:.6;cursor:not-allowed}
    .muted{color:var(--muted)}
    .preview{width:100%;aspect-ratio:1/1;object-fit:contain;border:1px dashed var(--border);border-radius:12px;background:#00000008}
    footer{margin-top:18px;color:var(--muted);text-align:center}
    .note{font-size:13px;color:var(--muted)}
  </style>
</head>
<body>
  <div class="container">
    <div class="card">
      <h1>Image Stamp Tester</h1>
      <p class="muted">Upload an image, choose your watermark text and position, then click <b>Stamp</b>.</p>

      <div class="row">
        <div>
          <label>Image file</label>
          <input id="file" type="file" accept="image/*" />

          <label>Watermark text</label>
          <input id="text" type="text" placeholder="Autodate" value="Autodate" />

          <label>Position</label>
          <select id="position">
            <option>center</option>
            <option>top-left</option>
            <option>top-right</option>
            <option>bottom-left</option>
            <option selected>bottom-right</option>
          </select>

          <label>Text size (px)</label>
          <input id="size" type="range" min="20" max="160" value="72" />
          <div class="note"><span id="sizeVal">72</span> px</div>

          <label>Opacity (%)</label>
          <input id="opacity" type="range" min="20" max="100" value="60" />
          <div class="note"><span id="opacityVal">60</span>%</div>

          <button id="go" class="btn">Stamp</button>
        </div>

        <div>
          <img id="out" class="preview" alt="Stamped preview will appear here" />
          <div style="margin-top:10px">
            <a id="download" class="muted" href="#" download="stamped.png" style="display:none">Download stamped image</a>
          </div>
        </div>
      </div>
    </div>

    <footer>Need changes (logo, diagonal watermark, color)? Tell me and I’ll update.</footer>
  </div>

  <script>
    const size = document.getElementById('size');
    const opacity = document.getElementById('opacity');
    size.addEventListener('input', () => document.getElementById('sizeVal').textContent = size.value);
    opacity.addEventListener('input', () => document.getElementById('opacityVal').textContent = opacity.value);

    document.getElementById('go').addEventListener('click', async () => {
      const file = document.getElementById('file').files[0];
      if(!file){ alert('Choose an image first'); return; }

      const fd = new FormData();
      fd.append('file', file);
      fd.append('text', document.getElementById('text').value);
      fd.append('position', document.getElementById('position').value);
      fd.append('size', size.value);
      fd.append('opacity', opacity.value);

      const btn = document.getElementById('go');
      const prev = btn.textContent; btn.textContent='Stamping…'; btn.disabled = true;

      try{
        const res = await fetch('/api/stamp', { method:'POST', body: fd });
        if(!res.ok) throw new Error('HTTP '+res.status);
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const img = document.getElementById('out');
        img.src = url;
        const dl = document.getElementById('download');
        dl.href = url; dl.style.display = 'inline';
      }catch(e){
        console.error(e); alert('Stamp failed.');
      }finally{
        btn.textContent = prev; btn.disabled = false;
      }
    });
  </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)

# ----------------------- Billing page kept -----------------------
BILLING_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Billing · Autodate</title>
  <style>
    :root{
      --bg:#f6f7fb; --card:#ffffff; --text:#111827; --muted:#6b7280; --border:#e5e7eb;
      --accent:#4f46e5; --accent-700:#3730a3; --success:#059669; --shadow:0 10px 20px rgba(0,0,0,.06);
      --radius:16px; --radius-sm:10px;
    }
    @media (prefers-color-scheme: dark) {
      :root{ --bg:#0f1221; --card:#12162b; --text:#e5e7eb; --muted:#9ca3af; --border:#232743; --shadow:0 10px 22px rgba(0,0,0,.35); }
    }
    *{box-sizing:border-box} html,body{height:100%}
    body{margin:0;background:var(--bg);color:var(--text);font:16px/1.45 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;}
    .container{max-width:1040px;margin:32px auto;padding:0 20px}
    .header{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}
    .brand{display:flex;gap:10px;align-items:center}
    .logo{width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,var(--accent),#7c3aed);box-shadow:var(--shadow)}
    .title{font-weight:700;font-size:20px}
    a.back{color:var(--muted);text-decoration:none} a.back:hover{color:var(--text)}
    .grid{display:grid;grid-template-columns:1fr;gap:18px}
    @media(min-width:900px){ .grid{grid-template-columns: 1.1fr .9fr} }
    .card{background:var(--card); border:1px solid var(--border); border-radius:var(--radius); box-shadow:var(--shadow); padding:18px;}
    .card h2{margin:0 0 10px 0;font-size:18px}
    .muted{color:var(--muted)}
    .balance{display:flex;justify-content:space-between;align-items:center;gap:16px;background:linear-gradient(180deg,rgba(79,70,229,.08),transparent);border-radius:10px; padding:14px 16px; border:1px dashed var(--border); margin-bottom:14px;}
    .kpis{display:flex;gap:18px;flex-wrap:wrap}
    .kpi .label{color:var(--muted);font-size:13px} .kpi .value{font-weight:700;font-size:22px}
    .btn{appearance:none;border:0;cursor:pointer;font-weight:600;background:linear-gradient(135deg,var(--accent),var(--accent-700));color:#fff; padding:12px 16px;border-radius:12px; box-shadow:0 8px 16px rgba(79,70,229,.35); }
    table{width:100%;border-collapse:separate;border-spacing:0;margin-top:6px}
    thead th{text-align:left;font-size:13px;color:var(--muted);font-weight:600;padding:12px;border-bottom:1px solid var(--border)}
    tbody td{padding:14px 12px;border-bottom:1px solid var(--border)} tbody tr:last-child td{border-bottom:0}
    .empty{text-align:center;color:var(--muted);padding:28px;border:1px dashed var(--border);border-radius:12px;margin-top:8px}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <a href="/" class="back">← Back</a>
      <div class="brand"><div class="logo"></div><div class="title">Autodate · Billing</div></div>
    </div>

    <div class="grid">
      <section class="card">
        <div class="balance">
          <div class="kpis">
            <div class="kpi"><div class="label">Credits</div><div class="value">0</div></div>
            <div class="kpi"><div class="label">Price</div><div class="value">£10 / credit</div></div>
            <div class="kpi"><div class="label">Minimum top-up</div><div class="value">5 credits (£50)</div></div>
          </div>
          <button class="btn" id="topup">Top up 5 credits (£50)</button>
        </div>

        <h2>Recent Top-ups</h2>
        <div class="empty">No top-ups yet</div>

        <h2 style="margin-top:18px">Recent Usage</h2>
        <div class="empty">No usage yet</div>

        <p class="muted" style="margin-top:14px">Embedded template. Ready to wire to real data.</p>
      </section>

      <aside class="card">
        <h2>Account Summary</h2>
        <ul class="muted" style="padding-left:18px; margin:10px 0 0 0;">
          <li>Plan: <strong>Pay-as-you-go</strong></li>
          <li>Billing currency: <strong>GBP (£)</strong></li>
          <li>Invoices: <a href="#" class="muted" onclick="alert('Coming soon'); return false;">view history</a></li>
          <li>Support: <a href="mailto:support@autodate.co.uk">support@autodate.co.uk</a></li>
        </ul>
      </aside>
    </div>
  </div>

  <script>
    document.getElementById('topup').addEventListener('click', async () => {
      const res = await fetch('/api/ping'); const data = await res.json();
      alert(`Backend says ok=${data.ok}, message="${data.message}"`);
    });
  </script>
</body>
</html>
"""

@app.get("/billing", response_class=HTMLResponse)
async def billing() -> HTMLResponse:
    return HTMLResponse(BILLING_HTML)
