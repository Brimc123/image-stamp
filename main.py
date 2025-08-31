# main.py — external JS (no inline handlers), credits + billing + admin
from __future__ import annotations

import io, os, csv, json, zipfile, tempfile
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse

from PIL import Image, ImageDraw, ImageFont, ImageOps

from auth import (
    router as auth_router,
    get_current_user,
    db_decrement_credit,
    db_increment_credit,
    db_log_usage,
)

APP_ENV = os.environ.get("APP_ENV", "prod")
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
ADMIN_SECRET = os.environ.get("ADMIN_SECRET")
DB_FILE = os.environ.get("DB_FILE", "/var/data/app.db")

CREDIT_COST_GBP = 10
MIN_TOPUP_CREDITS = 5

app = FastAPI(title="Time & Date Stamp")

if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# ---------- stamping utils ----------
def _font_path() -> str:
    for p in [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if os.path.exists(p): return p
    return ""

def _natural_text(ts: datetime) -> str:
    day = str(int(ts.strftime("%d"))); month = ts.strftime("%b"); year = ts.strftime("%Y")
    time_12 = ts.strftime("%I:%M:%S %p").lower()
    return f"{day} {month} {year}, {time_12}"

def _parse_times(date_text: str, start_str: str, end_str: str, n: int) -> List[datetime]:
    d = datetime.strptime(date_text.strip(), "%d/%m/%Y").date()
    def _p(s: str) -> datetime:
        s = s.strip()
        for fmt in ("%H:%M:%S", "%I:%M:%S %p"):
            try:
                return datetime.combine(d, datetime.strptime(s, fmt).time())
            except ValueError:
                pass
        raise ValueError("Time must be HH:MM:SS (24h) or hh:MM:SS am/pm")
    start_dt = _p(start_str); end_dt = _p(end_str)
    if end_dt <= start_dt: end_dt += timedelta(days=1)
    if n < 1: n = 1
    if n == 1: return [start_dt]
    step = (end_dt - start_dt).total_seconds() / (n - 1)
    return [start_dt + timedelta(seconds=i*step) for i in range(n)]

def _stamp_image(img: Image.Image, text: str, crop_height: int, *, font_px: int = 48) -> Image.Image:
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
    pad_x, pad_y = int(0.02 * w), int(0.02 * h)
    tx, ty = draw.textsize(text, font=font)
    x, y = pad_x, h - pad_y - ty
    for dx, dy in ((2,2),(0,2),(2,0)):
        draw.text((x+dx, y+dy), text, fill=(0,0,0), font=font)
    draw.text((x, y), text, fill=(255,255,255), font=font)
    return img

def _save_zip(images: List[str]) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip"); tmp.close()
    with zipfile.ZipFile(tmp.name, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for fp in images:
            z.write(fp, arcname=os.path.basename(fp))
    return tmp.name

def awaitable_read(up: UploadFile) -> bytes:
    return up.file.read()

def _extract_uploads(files: List[UploadFile]) -> List[str]:
    paths: List[str] = []
    for up in files:
        if not up.filename: continue
        name = up.filename.lower()
        if name.endswith(".zip"):
            data = awaitable_read(up)
            with tempfile.TemporaryDirectory() as td:
                zp = os.path.join(td, "in.zip")
                with open(zp, "wb") as f: f.write(data)
                with zipfile.ZipFile(zp, "r") as z:
                    for info in z.infolist():
                        if info.is_dir(): continue
                        if info.filename.lower().endswith((".jpg",".jpeg",".png")):
                            out = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(info.filename)[1])
                            with z.open(info, "r") as src, open(out.name, "wb") as dst:
                                dst.write(src.read())
                            paths.append(out.name)
        else:
            ext = ".jpg" if name.endswith((".jpg",".jpeg")) else ".png"
            out = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            out.write(awaitable_read(up)); out.flush(); out.close()
            paths.append(out.name)
    if not paths: raise HTTPException(status_code=400, detail="No images found")
    return paths

def _process_and_zip(files: List[UploadFile], date_text: str, start_time: str, end_time: str, crop_height: int) -> Tuple[str,int]:
    src_paths = _extract_uploads(files)
    stamps = _parse_times(date_text, start_time, end_time, len(src_paths))
    outs: List[str] = []
    for src, ts in zip(src_paths, stamps):
        with Image.open(src) as im:
            stamped = _stamp_image(im, _natural_text(ts), crop_height, font_px=52)
            out = tempfile.NamedTemporaryFile(delete=False, suffix="_stamped.jpg")
            stamped.save(out.name, "JPEG", quality=92)
            outs.append(out.name)
    return _save_zip(outs), len(outs)

# ---------- deps ----------
def require_user(user = Depends(get_current_user)):
    if not user: raise HTTPException(status_code=401, detail="Not logged in")
    return user

def _assert_admin(request: Request):
    try:
        user = get_current_user(request)
        if user and bool(user.get("is_admin")): return True
    except Exception: pass
    token = request.headers.get("X-Admin-Secret") or request.query_params.get("admin_secret")
    if ADMIN_SECRET and token == ADMIN_SECRET: return True
    raise HTTPException(status_code=403, detail="Forbidden")

# ---------- pages ----------
APP_HTML = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
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
small{color:var(--muted)}
hr{border:0;border-top:1px solid var(--line);margin:14px 0}
#status{min-height:24px}
.hidden{display:none}.bad{color:var(--bad)}.ok{color:#22c55e}
</style></head><body>
<div class="wrap">
  <h1>Time & Date Stamp</h1>
  <div class="card">
    <div class="row">
      <form id="authForm">
        <label>Email</label>
        <input id="email" type="email" required placeholder="you@example.com" style="width:260px"/>
        <label>Password</label>
        <input id="pw" type="password" required placeholder="••••••" style="width:200px"/>
        <button type="button" id="btnLogin">Login</button>
        <button type="button" id="btnSignup">Sign up</button>
        <button type="button" id="btnLogout">Logout</button>
      </form>
    </div>
    <div class="row">
      <small id="me">Not signed in</small>
      <small id="pricing"></small>
      <button class="link" id="btnBilling">Billing / Top up</button>
      <span id="adminLink" class="hidden"> · <a href="/billing" style="color:#fff">Admin</a></span>
    </div>
  </div>

  <div class="card">
    <form id="stampForm">
      <div class="row">
        <div><label>Stamp images</label>
          <input type="file" id="files" name="files" multiple accept=".jpg,.jpeg,.png,.zip"/></div>
        <div><label>Date (dd/mm/yyyy)</label>
          <input id="date" name="date" placeholder="dd/mm/yyyy" style="width:130px"/></div>
        <div><label>Crop height (px from bottom)</label>
          <input id="crop" name="crop" type="number" value="120" style="width:120px"/></div>
      </div>
      <div class="row" style="margin-top:8px">
        <div><label>Start time</label><input id="start" name="start" value="09:00:00" style="width:120px"/></div>
        <div><label>End time</label><input id="end" name="end" value="09:05:00" style="width:120px"/></div>
        <button type="submit" id="btnStamp">Stamp & Download (uses 1 credit)</button>
      </div>
      <div id="status"></div>
    </form>
    <small>We crop from the <b>bottom</b> first to remove any old stamp, then add your new one.</small>
  </div>
</div>
<script src="/static/app.js" defer></script>
</body></html>
"""

BILLING_HTML_TMPL = """<!doctype html><html><head>
<meta charset='utf-8'/><meta name='viewport' content='width=device-width,initial-scale=1'/>
<title>Billing</title>
<style>
body{margin:0;font:16px/1.45 system-ui,Segoe UI,Roboto,Helvetica,Arial;background:#0f172a;color:#e5e7eb}
.wrap{max-width:880px;margin:40px auto;padding:0 16px}
.card{background:#0b1224;border:1px solid #334155;border-radius:14px;padding:18px;box-shadow:0 6px 24px rgba(0,0,0,.25);margin-bottom:16px}
input,button{background:#0d1424;border:1px solid #334155;color:#e5e7eb;border-radius:10px;padding:9px 12px}
button{border:0;background:#2563eb;cursor:pointer}
small{color:#94a3b8}
table{width:100%;border-collapse:collapse} td,th{border-bottom:1px solid #334155;padding:8px;text-align:left}
.muted{color:#94a3b8}
</style></head><body>
<div class='wrap'>
  <div class='card'>
    <h2>Your billing</h2>
    <div id='me' class='muted'>Loading...</div>
    <p>Top-ups are billed weekly. Each click adds <b>{MIN}</b> credits (minimum) at £{GBP}/credit.</p>
    <div>
      <button id="btnTopupMin">Top up +{MIN} credits (£{MIN_TOTAL})</button>
      <input id="more" type="number" value="{MIN}" min="{MIN}" step="{MIN}" style="width:110px;margin-left:10px"/>
      <button id="btnTopupCustom">Top up (custom, multiples of {MIN})</button>
      <button id="btnBack" style="margin-left:10px;background:#374151">← Back</button>
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
      <button id="btnCSV">Download usage CSV (last 30 days)</button>
    </div>
  </div>
</div>
<script src="/static/billing.js" defer></script>
</body></html>
"""

# ---------- static JS ----------
APP_JS = r"""
(function(){
async function api(path, opts){
  const r = await fetch(path, Object.assign({credentials:'include'}, opts||{}));
  if(!r.ok){
    let t; try{ t = await r.json(); }catch(e){ t = await r.text(); }
    throw new Error((t && t.detail) ? t.detail : (t || 'Request failed'));
  }
  const ct = r.headers.get('content-type')||'';
  if(ct.includes('application/json')) return await r.json();
  return await r.blob();
}

async function refreshMe(){
  try{
    const pricing = await api('/auth/config');
    const p = document.querySelector('#pricing');
    if(p) p.textContent = '1 credit = £'+pricing.credit_cost_gbp+'. Min top-up = '+pricing.min_topup_credits+' credits';
  }catch(e){}
  try{
    const me = await api('/auth/me');
    document.querySelector('#me').textContent = 'Signed in as '+me.email+' · Credits: '+me.credits;
    if(me.is_admin){ document.querySelector('#adminLink').classList.remove('hidden'); }
  }catch(e){
    document.querySelector('#me').textContent = 'Not signed in';
    document.querySelector('#adminLink').classList.add('hidden');
  }
}

async function doLogin(){
  const email = document.querySelector('#email').value.trim();
  const pw = document.querySelector('#pw').value;
  await api('/auth/login', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({email, password: pw})});
  await refreshMe();
}

async function doSignup(){
  const email = document.querySelector('#email').value.trim();
  const pw = document.querySelector('#pw').value;
  await api('/auth/signup', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({email, password: pw})});
  await doLogin();
}

async function doLogout(){
  await api('/auth/logout', {method:'POST'});
  await refreshMe();
}

async function doStamp(e){
  e.preventDefault();
  const st = document.querySelector('#status');
  st.textContent = 'Processing...';
  const fd = new FormData(document.querySelector('#stampForm'));
  try{
    const blob = await api('/stamp', {method:'POST', body: fd});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'stamped_images.zip'; a.click();
    URL.revokeObjectURL(url);
    st.innerHTML = '<span class="ok">Done — 1 credit used.</span>';
    await refreshMe();
  }catch(err){
    st.innerHTML = '<span class="bad">'+err.message+'</span>';
  }
}

document.addEventListener('DOMContentLoaded', function(){
  const L = id => document.getElementById(id);
  L('btnLogin').addEventListener('click', doLogin);
  L('btnSignup').addEventListener('click', doSignup);
  L('btnLogout').addEventListener('click', doLogout);
  L('btnBilling').addEventListener('click', ()=>{ window.location.href='/billing'; });
  L('stampForm').addEventListener('submit', doStamp);
  refreshMe();
});
})();
"""

BILLING_JS = r"""
(function(){
async function api(path, opts){
  const r = await fetch(path, Object.assign({credentials:'include'}, opts||{}));
  if(!r.ok){
    let t; try{ t=await r.json(); }catch(e){ t=await r.text(); }
    throw new Error((t && t.detail) ? t.detail : (t||'Request failed'));
  }
  const ct=r.headers.get('content-type')||''; if(ct.includes('application/json')) return r.json(); return r.blob();
}

async function init(){
  try{
    const me = await api('/auth/me');
    document.querySelector('#me').textContent = me.email + ' · Credits: ' + me.credits;
    if(me.is_admin) document.querySelector('#admin').style.display='block';
    loadLog();
  }catch(e){ document.querySelector('#me').textContent='Not signed in'; }
}

async function topup(n){
  n = parseInt(n,10);
  const MIN = parseInt(document.querySelector('#more').getAttribute('min'),10) || 5;
  if(isNaN(n) || n < MIN || (n % MIN)!==0){ alert('Top-up must be multiples of '+MIN+'.'); return; }
  await api('/billing/topup', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({credits:n})});
  alert('Top-up added. You will be invoiced weekly.'); location.reload();
}

async function loadLog(){
  const rows = await api('/billing/my-log');
  const tb = document.querySelector('#log tbody'); tb.innerHTML='';
  rows.forEach(r=>{
    const tr=document.createElement('tr');
    tr.innerHTML = '<td>'+r.created_at.replace('T',' ').slice(0,19)+'</td><td>'+r.endpoint+'</td><td>'+ (r.meta||'') +'</td>';
    tb.appendChild(tr);
  });
}

async function downloadCSV(){
  const blob = await api('/admin/usage.csv?days=30');
  const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'usage.csv'; a.click(); URL.revokeObjectURL(url);
}

document.addEventListener('DOMContentLoaded', function(){
  document.getElementById('btnTopupMin').addEventListener('click', ()=>topup(parseInt(document.getElementById('more').getAttribute('min'),10)));
  document.getElementById('btnTopupCustom').addEventListener('click', ()=>topup(document.getElementById('more').value));
  document.getElementById('btnBack').addEventListener('click', ()=>{ location.href='/app'; });
  document.getElementById('btnCSV').addEventListener('click', downloadCSV);
  init();
});
})();
"""

# serve JS
@app.get("/static/app.js")
def app_js():
    return PlainTextResponse(APP_JS, media_type="application/javascript")

@app.get("/static/billing.js")
def billing_js():
    return PlainTextResponse(BILLING_JS, media_type="application/javascript")

# ---------- routes ----------
@app.get("/health")
def health(): return {"ok": True}

app.include_router(auth_router, prefix="/auth", tags=["auth"])

@app.get("/", response_class=HTMLResponse)
@app.get("/app", response_class=HTMLResponse)
def app_ui(): return HTMLResponse(APP_HTML)

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
    try:
        zip_path, count = _process_and_zip(files, date, start, end, int(crop))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}")

    db_decrement_credit(user["id"], amount=1)
    db_log_usage(user["id"], "stamp", {"count": count, "crop": int(crop)})

    filename = f"stamped_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
    return FileResponse(zip_path, media_type="application/zip", filename=filename)

@app.get("/billing", response_class=HTMLResponse)
def billing_page(request: Request):
    html = BILLING_HTML_TMPL.format(
        MIN=MIN_TOPUP_CREDITS, GBP=CREDIT_COST_GBP, MIN_TOTAL=MIN_TOPUP_CREDITS*CREDIT_COST_GBP
    )
    return HTMLResponse(html)

def _invoice_week(dt: Optional[datetime] = None) -> str:
    dt = dt or datetime.utcnow(); year, week, _ = dt.isocalendar(); return f"{year}-W{week:02d}"

@app.post("/billing/topup")
def billing_topup(payload: dict, user = Depends(require_user)):
    credits = int(payload.get("credits") or 0)
    if credits < MIN_TOPUP_CREDITS or credits % MIN_TOPUP_CREDITS != 0:
        raise HTTPException(status_code=400, detail=f"Minimum top-up is {MIN_TOPUP_CREDITS} credits, in multiples of {MIN_TOPUP_CREDITS}.")
    db_increment_credit(user["id"], amount=credits)
    meta = {"credits": credits, "amount_gbp": credits*CREDIT_COST_GBP, "invoice_week": _invoice_week(), "status": "pending_invoice"}
    db_log_usage(user["id"], "topup", meta)
    return {"ok": True}

@app.get("/billing/my-log")
def my_log(user = Depends(require_user)):
    import sqlite3
    con = sqlite3.connect(DB_FILE); con.row_factory = sqlite3.Row
    cur = con.execute("SELECT created_at, endpoint, meta FROM usage_log WHERE user_id=? ORDER BY id DESC LIMIT 50", (user["id"],))
    rows = [{"created_at": r["created_at"], "endpoint": r["endpoint"], "meta": r["meta"]} for r in cur.fetchall()]
    con.close(); return rows

@app.post("/admin/topup")
def admin_topup(payload: dict, request: Request):
    _assert_admin(request)
    import sqlite3
    email = (payload.get("email") or "").strip().lower(); credits = int(payload.get("credits") or 0)
    if not email or credits <= 0: raise HTTPException(status_code=400, detail="email and positive credits required")
    con = sqlite3.connect(DB_FILE); con.row_factory = sqlite3.Row
    cur = con.execute("SELECT id FROM users WHERE email=?", (email,)); row = cur.fetchone(); con.close()
    if not row: raise HTTPException(status_code=404, detail="User not found")
    db_increment_credit(row["id"], amount=credits)
    db_log_usage(row["id"], "admin_topup", {"credits": credits, "by": "admin"})
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
    out = io.StringIO(); w = csv.writer(out); w.writerow(["email","endpoint","created_at","meta"])
    for r in rows: w.writerow([r["email"], r["endpoint"], r["created_at"], r["meta"]])
    return Response(content=out.getvalue(), media_type="text/csv")

@app.get("/admin/summary")
def admin_summary(request: Request):
    _assert_admin(request)
    import sqlite3
    con = sqlite3.connect(DB_FILE); con.row_factory = sqlite3.Row
    totals = {}
    cur = con.execute("SELECT COUNT(*) AS c FROM users"); totals["users"] = cur.fetchone()["c"]
    cur = con.execute("SELECT SUM(credits) AS s FROM users"); totals["credits_outstanding"] = cur.fetchone()["s"] or 0
    cur = con.execute("SELECT endpoint, COUNT(*) as c FROM usage_log WHERE created_at >= datetime('now','-7 days') GROUP BY endpoint")
    totals["events_last7"] = {r["endpoint"]: r["c"] for r in cur.fetchall()}
    cur = con.execute("SELECT meta FROM usage_log WHERE endpoint IN ('topup','admin_topup') AND created_at >= datetime('now','-7 days')")
    gbp = 0.0
    for r in cur.fetchall():
        try: gbp += float((json.loads(r["meta"] or "{}")).get("amount_gbp") or 0.0)
        except Exception: pass
    totals["billable_gbp_last7"] = gbp
    con.close(); return totals
