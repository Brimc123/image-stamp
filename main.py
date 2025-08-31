# main.py — Step 2: app routes, credit deduction, stamping, top-ups, admin
from __future__ import annotations

import io
import os
import csv
import json
import zipfile
import tempfile
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from fastapi import (
    FastAPI, Depends, HTTPException, Request, Response, UploadFile, File, Form
)
    # NOTE: fastapi + starlette are required in requirements.txt
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse

from PIL import Image, ImageDraw, ImageFont, ImageOps

# Import auth helpers
from auth import (
    router as auth_router,
    get_current_user,
    db_decrement_credit,
    db_increment_credit,
    db_log_usage,
)

# ------------------------
# Config
# ------------------------
APP_ENV = os.environ.get("APP_ENV", "prod")
ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()
]
SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "imgstamp_session")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET")  # used for admin-only endpoints
DB_FILE = os.environ.get("DB_FILE", "/var/data/app.db")

CREDIT_COST_GBP = 10  # £10 per credit
MIN_TOPUP_CREDITS = 5

app = FastAPI(title="Time & Date Stamp")

# CORS for the web UI if a separate domain is used
if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# ------------------------
# Utilities (stamping)
# ------------------------
def _font_path() -> str:
    candidates = [
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return ""

def _natural_text(ts: datetime) -> str:
    # "27 Aug 2025, 09:03:34 am"
    day = str(int(ts.strftime("%d")))
    month = ts.strftime("%b")
    year = ts.strftime("%Y")
    time_12 = ts.strftime("%I:%M:%S %p").lower()
    return f"{day} {month} {year}, {time_12}"

def _parse_times(date_text: str, start_str: str, end_str: str, n: int) -> List[datetime]:
    """Parse dd/mm/yyyy and hh:mm:ss to a list of n timestamps spread evenly."""
    d = datetime.strptime(date_text.strip(), "%d/%m/%Y").date()
    def _p(s: str) -> datetime:
        s = s.strip()
        for fmt in ("%H:%M:%S", "%I:%M:%S %p"):
            try:
                t = datetime.strptime(s, fmt).time()
                return datetime.combine(d, t)
            except ValueError:
                continue
        raise ValueError("Time must be HH:MM:SS (24h) or hh:MM:SS am/pm")
    start_dt = _p(start_str)
    end_dt = _p(end_str)
    if end_dt <= start_dt:
        end_dt = end_dt + timedelta(days=1)
    if n < 1:
        n = 1
    span = (end_dt - start_dt).total_seconds()
    if n == 1:
        return [start_dt]
    step = span / (n - 1)
    return [start_dt + timedelta(seconds=i * step) for i in range(n)]

def _stamp_image(img: Image.Image, text: str, crop_height: int, *, font_px: int = 48) -> Image.Image:
    """Bottom-crop then lay text close to bottom, white with soft shadow."""
    img = ImageOps.exif_transpose(img).copy()
    w, h = img.size
    ch = max(0, min(int(crop_height), h - 1))
    if ch > 0:
        img = img.crop((0, 0, w, h - ch))
        w, h = img.size

    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(_font_path() or "arial.ttf", font_px)
    except Exception:
        font = ImageFont.load_default()

    # place near bottom-left with small padding
    pad_x, pad_y = int(0.02 * w), int(0.02 * h)
    tx, ty = draw.textsize(text, font=font)
    x = pad_x
    y = h - pad_y - ty

    # soft shadow
    for dx, dy in ((2,2), (0,2), (2,0)):
        draw.text((x+dx, y+dy), text, fill=(0,0,0), font=font)
    draw.text((x, y), text, fill=(255,255,255), font=font)
    return img

def _save_zip(images: List[str]) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp.close()
    with zipfile.ZipFile(tmp.name, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for fp in images:
            arc = os.path.basename(fp)
            z.write(fp, arcname=arc)
    return tmp.name

def awaitable_read(up: UploadFile) -> bytes:
    # Starlette's UploadFile can be sync-read safely here
    return up.file.read()

def _extract_uploads(files: List[UploadFile]) -> List[str]:
    """Accept JPG/PNG or one .zip, return list of temp image file paths."""
    paths: List[str] = []
    for up in files:
        if not up.filename:
            continue
        name = up.filename.lower()
        # If a zip is given, expand it
        if name.endswith(".zip"):
            data = awaitable_read(up)
            with tempfile.TemporaryDirectory() as td:
                zip_path = os.path.join(td, "in.zip")
                with open(zip_path, "wb") as f:
                    f.write(data)
                with zipfile.ZipFile(zip_path, "r") as z:
                    for info in z.infolist():
                        if info.is_dir():
                            continue
                        if info.filename.lower().endswith((".jpg",".jpeg",".png")):
                            out = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(info.filename)[1])
                            with z.open(info, "r") as src, open(out.name, "wb") as dst:
                                dst.write(src.read())
                            paths.append(out.name)
        else:
            # single image
            ext = ".jpg" if name.endswith((".jpg",".jpeg")) else ".png"
            out = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            out.write(awaitable_read(up))
            out.flush(); out.close()
            paths.append(out.name)
    if not paths:
        raise HTTPException(status_code=400, detail="No images found")
    return paths

def _process_and_zip(
    files: List[UploadFile],
    date_text: str,
    start_time: str,
    end_time: str,
    crop_height: int,
) -> Tuple[str, int]:
    src_paths = _extract_uploads(files)
    stamps = _parse_times(date_text, start_time, end_time, len(src_paths))
    out_files: List[str] = []
    for src, ts in zip(src_paths, stamps):
        with Image.open(src) as im:
            stamped = _stamp_image(im, _natural_text(ts), crop_height, font_px=52)
            out = tempfile.NamedTemporaryFile(delete=False, suffix="_stamped.jpg")
            stamped.save(out.name, "JPEG", quality=92)
            out_files.append(out.name)
    zip_path = _save_zip(out_files)
    return zip_path, len(out_files)

# ------------------------
# Dependencies
# ------------------------
def require_user(user = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    return user

def require_admin_secret(request: Request):
    if not ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Admin not configured")
    token = request.headers.get("X-Admin-Secret") or request.query_params.get("admin_secret")
    if token != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    return True

def _assert_admin(request: Request):
    # Allow if logged in user is admin, OR if correct admin secret provided.
    try:
        user = get_current_user(request)
        if user and bool(user.get("is_admin")):
            return True
    except Exception:
        pass
    token = request.headers.get("X-Admin-Secret") or request.query_params.get("admin_secret")
    if ADMIN_SECRET and token == ADMIN_SECRET:
        return True
    raise HTTPException(status_code=403, detail="Forbidden")

# ------------------------
# HTML (simple app UI)
# ------------------------
APP_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Time & Date Stamp</title>
<style>
:root{--bg:#0f172a;--card:#0b1224;--text:#e5e7eb;--muted:#94a3b8;--line:#334155;--accent:#2563eb;--warn:#f59e0b;--bad:#ef4444}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.45 system-ui,Segoe UI,Roboto,Helvetica,Arial}
.wrap{max-width:980px;margin:36px auto;padding:0 18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:0 6px 24px rgba(0,0,0,.25);margin-bottom:16px}
h1{margin:0 0 10px;font-size:28px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
label{display:block;margin-bottom:6px;color:var(--muted)}
input,button{background:#0d1424;border:1px solid var(--line);color:var(--text);border-radius:10px;padding:9px 12px}
button{border:0;background:var(--accent);cursor:pointer}
button.link{background:transparent;border:0;color:var(--text);text-decoration:underline;cursor:pointer;padding:0}
button.warn{background:var(--warn);color:#111}
small{color:var(--muted)}
hr{border:0;border-top:1px solid var(--line);margin:14px 0}
#status{min-height:24px}
.hidden{display:none}
.bad{color:var(--bad)}
.ok{color:#22c55e}
</style>
</head>
<body>
  <div class="wrap">
    <h1>Time & Date Stamp</h1>

    <div class="card">
      <div class="row">
        <form id="authForm" onsubmit="onLogin(event)">
          <label>Email</label>
          <input id="email" type="email" required placeholder="you@example.com" style="width:260px"/>
          <label>Password</label>
          <input id="pw" type="password" required placeholder="••••••" style="width:200px"/>
          <button type="submit">Login</button>
          <button type="button" onclick="onSignup(event)">Sign up</button>
          <button type="button" onclick="onLogout()">Logout</button>
        </form>
      </div>
      <div class="row">
        <small id="me">Not signed in</small>
        <small id="pricing"></small>
        <button class="link" onclick="openBilling()">Billing / Top up</button>
        <span id="adminLink" class="hidden"> · <a href="/billing" style="color:#fff">Admin</a></span>
      </div>
    </div>

    <div class="card">
      <form id="stampForm" onsubmit="onStamp(event)">
        <div class="row">
          <div>
            <label>Stamp images</label>
            <input type="file" id="files" name="files" multiple accept=".jpg,.jpeg,.png,.zip" />
          </div>
          <div>
            <label>Date (dd/mm/yyyy)</label>
            <input id="date" name="date" placeholder="dd/mm/yyyy" style="width:130px"/>
          </div>
          <div>
            <label>Crop height (px from bottom)</label>
            <input id="crop" name="crop" type="number" value="120" style="width:120px"/>
          </div>
        </div>
        <div class="row" style="margin-top:8px">
          <div>
            <label>Start time</label>
            <input id="start" name="start" value="09:00:00" style="width:120px"/>
          </div>
          <div>
            <label>End time</label>
            <input id="end" name="end" value="09:05:00" style="width:120px"/>
          </div>
          <button type="submit">Stamp & Download (uses 1 credit)</button>
        </div>
        <div id="status"></div>
      </form>
      <small>We crop from the <b>bottom</b> first to remove any old stamp, then add your new one.</small>
    </div>
  </div>
<script>
async function api(path, opts){
  const r = await fetch(path, Object.assign({credentials:'include'}, opts||{}));
  if(!r.ok){
    let t; try{ t = await r.json(); }catch(e){ t = await r.text(); }
    throw new Error(t?.detail || t || 'Request failed');
  }
  const ct = r.headers.get('content-type')||'';
  if(ct.includes('application/json')) return await r.json();
  return await r.blob();
}
function £(n){ return '£'+n.toFixed(2); }

async function refreshMe(){
  const pricing = await api('/auth/config');
  document.querySelector('#pricing').textContent =
    `1 credit = £${pricing.credit_cost_gbp}. Min top-up = ${pricing.min_topup_credits} credits`;
  try{
    const me = await api('/auth/me');
    document.querySelector('#me').textContent =
      `Signed in as ${me.email} · Credits: ${me.credits}`;
    if(me.is_admin){ document.querySelector('#adminLink').classList.remove('hidden'); }
  }catch(e){
    document.querySelector('#me').textContent = 'Not signed in';
    document.querySelector('#adminLink').classList.add('hidden');
  }
}
async function onLogin(e){
  e.preventDefault();
  const email = document.querySelector('#email').value.trim();
  const pw = document.querySelector('#pw').value;
  await api('/auth/login', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({email, password: pw})});
  await refreshMe();
}
async function onSignup(e){
  const email = document.querySelector('#email').value.trim();
  const pw = document.querySelector('#pw').value;
  await api('/auth/signup', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({email, password: pw})});
  await onLogin(new Event('submit'));
}
async function onLogout(){
  await api('/auth/logout', {method:'POST'});
  await refreshMe();
}
function openBilling(){ window.location.href = '/billing'; }

async function onStamp(e){
  e.preventDefault();
  const st = document.querySelector('#status');
  st.textContent = 'Processing…';
  const fd = new FormData(document.querySelector('#stampForm'));
  try{
    const blob = await api('/stamp', {method:'POST', body: fd});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'stamped_images.zip';
    a.click();
    URL.revokeObjectURL(url);
    st.innerHTML = '<span class="ok">Done — 1 credit used.</span>';
    await refreshMe();
  }catch(err){
    st.innerHTML = '<span class="bad">'+err.message+'</span>';
  }
}

refreshMe();
</script>
</body></html>
"""

BILLING_HTML_TMPL = """<!doctype html><html><head>
<meta charset='utf-8'/><meta name='viewport' content='width=device-width,initial-scale=1'/>
<title>Billing</title>
<style>
  body{{margin:0;font:16px/1.45 system-ui,Segoe UI,Roboto,Helvetica,Arial;background:#0f172a;color:#e5e7eb}}
  .wrap{{max-width:880px;margin:40px auto;padding:0 16px}}
  .card{{background:#0b1224;border:1px solid #334155;border-radius:14px;padding:18px;box-shadow:0 6px 24px rgba(0,0,0,.25);margin-bottom:16px}}
  input,button{{background:#0d1424;border:1px solid #334155;color:#e5e7eb;border-radius:10px;padding:9px 12px}}
  button{{border:0;background:#2563eb;cursor:pointer}}
  small{{color:#94a3b8}}
  table{{width:100%;border-collapse:collapse}} td,th{{border-bottom:1px solid #334155;padding:8px;text-align:left}}
  .muted{{color:#94a3b8}}
</style></head><body>
<div class='wrap'>
  <div class='card'>
    <h2>Your billing</h2>
    <div id='me' class='muted'>Loading…</div>
    <p>Top-ups are billed weekly. Each click adds <b>{MIN}</b> credits (minimum) at £{GBP}/credit.</p>
    <div>
      <button onclick="topup({MIN})">Top up +{MIN} credits (£{MIN_TOTAL})</button>
      <input id="more" type="number" value="{MIN}" min="{MIN}" step="{MIN}" style="width:110px;margin-left:10px"/>
      <button onclick="topup(document.querySelector('#more').value)">Top up (custom, multiples of {MIN})</button>
      <button onclick="location.href='/app'" style="margin-left:10px;background:#374151">← Back</button>
    </div>
  </div>

  <div class='card'>
    <h3>My recent activity</h3>
    <table id="log"><thead><tr><th>When</th><th>Event</th><th>Meta</th></tr></thead><tbody></tbody></table>
  </div>

  <div class='card' id='admin' style='display:none'>
    <h3>Admin — organisation view</h3>
    <div class='muted'>Requires ADMIN_SECRET set on the server.</div>
    <div style='margin:10px 0'>
      <button onclick="downloadCSV()">Download usage CSV (last 30 days)</button>
    </div>
  </div>
</div>
<script>
async function api(path, opts){{ const r = await fetch(path, Object.assign({{credentials:'include'}}, opts||{{}})); if(!r.ok){{ throw new Error((await r.json()).detail||'Request failed'); }} const ct=r.headers.get('content-type')||''; if(ct.includes('application/json')) return r.json(); return r.blob(); }}
async function init(){{
  try{{
    const me = await api('/auth/me');
    document.querySelector('#me').textContent = me.email + ' · Credits: ' + me.credits;
    if(me.is_admin) document.querySelector('#admin').style.display='block';
    loadLog();
  }}catch(e){{ document.querySelector('#me').textContent='Not signed in'; }}
}}
async function topup(n){{
  n = parseInt(n,10);
  if(isNaN(n) || n < {MIN} || (n % {MIN}) !== 0){{ alert('Top-up must be multiples of {MIN}.'); return; }}
  await api('/billing/topup', {{method:'POST', headers:{{'content-type':'application/json'}}, body: JSON.stringify({{credits:n}})}});
  alert('Top-up added. You will be invoiced weekly.'); location.reload();
}}
async function loadLog(){{
  const rows = await api('/billing/my-log');
  const tb = document.querySelector('#log tbody'); tb.innerHTML='';
  rows.forEach(r=>{{
    const tr=document.createElement('tr');
    tr.innerHTML = '<td>'+r.created_at.replace('T',' ').slice(0,19)+'</td><td>'+r.endpoint+'</td><td>'+ (r.meta||'') +'</td>';
    tb.appendChild(tr);
  }});
}}
async function downloadCSV(){{
  const blob = await api('/admin/usage.csv?days=30');
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = 'usage.csv'; a.click(); URL.revokeObjectURL(url);
}}
init();
</script>
</body></html>
"""

# ------------------------
# Routes
# ------------------------
@app.get("/health")
def health():
    return {"ok": True}

# Auth sub-router
app.include_router(auth_router, prefix="/auth", tags=["auth"])

@app.get("/", response_class=HTMLResponse)
@app.get("/app", response_class=HTMLResponse)
def app_ui():
    return HTMLResponse(APP_HTML)

@app.post("/stamp")
async def stamp_endpoint(
    request: Request,
    files: List[UploadFile] = File(...),
    date: str = Form(...),
    start: str = Form(...),
    end: str = Form(...),
    crop: int = Form(120),
    user = Depends(require_user),
):
    # Process first; only deduct on success
    try:
        zip_path, count = _process_and_zip(files, date, start, end, int(crop))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}")

    # Deduct 1 credit and log usage
    db_decrement_credit(user["id"], amount=1)
    db_log_usage(user["id"], "stamp", {"count": count, "crop": int(crop)})

    filename = f"stamped_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
    return FileResponse(zip_path, media_type="application/zip", filename=filename)

# -------- Billing (user) --------
@app.get("/billing", response_class=HTMLResponse)
def billing_page(request: Request):
    html = BILLING_HTML_TMPL.format(
        MIN=MIN_TOPUP_CREDITS,
        GBP=CREDIT_COST_GBP,
        MIN_TOTAL=MIN_TOPUP_CREDITS * CREDIT_COST_GBP,
    )
    return HTMLResponse(html)

def _invoice_week(dt: Optional[datetime] = None) -> str:
    dt = dt or datetime.utcnow()
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"

# -- Billing API
@app.post("/billing/topup")
def billing_topup(payload: dict, user = Depends(require_user)):
    # Accept multiples of MIN_TOPUP_CREDITS; log for weekly invoice
    credits = int(payload.get("credits") or 0)
    if credits < MIN_TOPUP_CREDITS or credits % MIN_TOPUP_CREDITS != 0:
        raise HTTPException(status_code=400, detail=f"Minimum top-up is {MIN_TOPUP_CREDITS} credits, in multiples of {MIN_TOPUP_CREDITS}.")
    db_increment_credit(user["id"], amount=credits)
    meta = {
        "credits": credits,
        "amount_gbp": credits * CREDIT_COST_GBP,
        "invoice_week": _invoice_week(),
        "status": "pending_invoice",
    }
    db_log_usage(user["id"], "topup", meta)
    return {"ok": True}

@app.get("/billing/my-log")
def my_log(user = Depends(require_user)):
    import sqlite3
    con = sqlite3.connect(DB_FILE); con.row_factory = sqlite3.Row
    cur = con.execute("SELECT created_at, endpoint, meta FROM usage_log WHERE user_id=? ORDER BY id DESC LIMIT 50", (user["id"],))
    rows = [{"created_at": r["created_at"], "endpoint": r["endpoint"], "meta": r["meta"]} for r in cur.fetchall()]
    con.close()
    return rows

# -------- Admin (reports & manual top-ups) --------
@app.post("/admin/topup")
def admin_topup(payload: dict, request: Request):
    _assert_admin(request)
    import sqlite3
    email = (payload.get("email") or "").strip().lower()
    credits = int(payload.get("credits") or 0)
    if not email or credits <= 0:
        raise HTTPException(status_code=400, detail="email and positive credits required")
    con = sqlite3.connect(DB_FILE); con.row_factory = sqlite3.Row
    cur = con.execute("SELECT id FROM users WHERE email=?", (email,))
    row = cur.fetchone()
    if not row:
        con.close()
        raise HTTPException(status_code=404, detail="User not found")
    user_id = row["id"]; con.close()
    db_increment_credit(user_id, amount=credits)
    db_log_usage(user_id, "admin_topup", {"credits": credits, "by": "admin"})
    return {"ok": True}

@app.get("/admin/usage.csv")
def admin_usage_csv(request: Request, days: int = 30):
    _assert_admin(request)
    import sqlite3
    con = sqlite3.connect(DB_FILE); con.row_factory = sqlite3.Row
    cur = con.execute(
        "SELECT u.email, l.endpoint, l.created_at, l.meta "
        "FROM usage_log l JOIN users u ON u.id = l.user_id "
        "WHERE l.created_at >= datetime('now', ?)"
        "ORDER BY l.id DESC",
        (f"-{int(days)} days",),
    )
    rows = cur.fetchall(); con.close()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["email","endpoint","created_at","meta"])
    for r in rows:
        w.writerow([r["email"], r["endpoint"], r["created_at"], r["meta"]])
    return Response(content=out.getvalue(), media_type="text/csv")

@app.get("/admin/summary")
def admin_summary(request: Request):
    _assert_admin(request)
    import sqlite3
    con = sqlite3.connect(DB_FILE); con.row_factory = sqlite3.Row
    totals = {}
    cur = con.execute("SELECT COUNT(*) AS c FROM users"); totals["users"] = cur.fetchone()["c"]
    cur = con.execute("SELECT SUM(credits) AS s FROM users"); totals["credits_outstanding"] = cur.fetchone()["s"] or 0
    cur = con.execute(
        "SELECT endpoint, COUNT(*) as c FROM usage_log WHERE created_at >= datetime('now','-7 days') GROUP BY endpoint"
    )
    totals["events_last7"] = {r["endpoint"]: r["c"] for r in cur.fetchall()}
    cur = con.execute(
        "SELECT meta FROM usage_log WHERE endpoint IN ('topup','admin_topup') AND created_at >= datetime('now','-7 days')"
    )
    gbp = 0.0
    for r in cur.fetchall():
        try:
            m = json.loads(r["meta"] or "{}")
            gbp += float(m.get("amount_gbp") or 0.0)
        except Exception:
            continue
    totals["billable_gbp_last7"] = gbp
    con.close()
    return totals
