# main.py
import os
import io
import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

import bcrypt
from PIL import Image, ImageDraw, ImageFont

APP_ENV = os.getenv("APP_ENV", "development")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev_secret_change_me")
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "imgstamp_session")
DB_FILE = os.getenv("DB_FILE", os.getenv("DB_PATH", "./app.db"))
CREDIT_COST_GBP = float(os.getenv("CREDIT_COST_GBP", "10"))
MIN_TOPUP = int(os.getenv("MIN_TOPUP", "5"))

# -----------------------------------------------------------------------------
# Database helpers
# -----------------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,          -- 'topup' or 'stamp'
            credits INTEGER NOT NULL,      -- + for topup, - for usage
            unit_price REAL DEFAULT 0,     -- price per credit (topups)
            total_price REAL DEFAULT 0,    -- unit * credits (topups)
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()

def user_balance(user_id: int) -> int:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(credits),0) AS bal FROM ledger WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return int(row["bal"] or 0)

# -----------------------------------------------------------------------------
# App + middleware
# -----------------------------------------------------------------------------
init_db()

app = FastAPI()
if ALLOWED_ORIGINS != ["*"]:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie=SESSION_COOKIE_NAME,
    same_site="lax",
    https_only=True if APP_ENV == "production" else False,
)

# -----------------------------------------------------------------------------
# Auth helpers
# -----------------------------------------------------------------------------
def current_user(request: Request) -> Optional[sqlite3.Row]:
    uid = request.session.get("uid")
    if not uid:
        return None
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, email, is_admin, created_at FROM users WHERE id=?", (uid,))
    return cur.fetchone()

def require_user(request: Request) -> sqlite3.Row:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    return user

# -----------------------------------------------------------------------------
# HTML (embedded)
# -----------------------------------------------------------------------------
BILLING_HTML = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Billing · AutoDate</title>
    <style>
      :root { --bg:#0f172a; --card:#111827; --muted:#94a3b8; --text:#e5e7eb; --brand:#7c3aed; --ok:#22c55e; --bad:#ef4444; }
      * { box-sizing: border-box; }
      body { margin:0; font-family: ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial; background:var(--bg); color:var(--text); }
      .wrap { max-width: 980px; margin: 40px auto; padding: 0 16px; }
      h1 { font-size: 34px; margin: 0 0 12px; }
      .muted { color: var(--muted); font-size: 14px; }
      .card { background: var(--card); border: 1px solid #1f2937; border-radius: 16px; padding: 16px; }
      .row { display:flex; gap:16px; align-items:center; }
      .row > * { flex:1; }
      button { background: var(--brand); color:white; border:0; padding:12px 16px; border-radius: 12px; font-weight:600; cursor:pointer; }
      button.secondary { background: transparent; border:1px solid #334155; }
      table { width:100%; border-collapse: collapse; }
      th, td { padding:12px 10px; border-top: 1px solid #1f2937; }
      th { text-align:left; color: var(--muted); font-weight:600; }
      .right { text-align:right; }
      input[type="email"], input[type="password"] { width: 100%; padding:12px; border-radius: 10px; border:1px solid #334155; background:#0b1220; color:var(--text); }
      .stack { display:grid; gap:10px; }
      .pill { display:inline-block; padding:4px 10px; border-radius:999px; background:#0b1220; border:1px solid #334155; font-size:12px; color:var(--muted); }
      .warn { color:#fbbf24; }
      .success { color: var(--ok); }
      .center { text-align:center; }
    </style>
  </head>
  <body>
    <div class="wrap">
      <a href="/" class="muted">← Back</a>
      <h1>Billing</h1>

      <div class="card" style="margin-bottom:16px;">
        <div id="authArea" class="row">
          <div>
            <div class="muted">Status</div>
            <div id="whoami" style="font-weight:700">Loading…</div>
          </div>
          <div class="right">
            <button id="logoutBtn" class="secondary" style="display:none;">Log out</button>
          </div>
        </div>
        <div id="loginArea" class="row" style="margin-top:10px; display:none;">
          <div class="stack">
            <input id="email" type="email" placeholder="you@example.com" />
          </div>
          <div class="stack">
            <input id="password" type="password" placeholder="password" />
          </div>
          <div class="right">
            <button id="signupBtn" class="secondary">Sign up</button>
            <button id="loginBtn">Log in</button>
          </div>
        </div>
      </div>

      <div class="card" style="margin-bottom:16px;">
        <div class="row">
          <div><span class="muted">Credits:</span> <span id="credits">0</span></div>
          <div><span class="muted">Price:</span> £<span id="pricePer">X</span>/credit</div>
          <div><span class="muted">Minimum top-up:</span> <span id="minTopup">X</span> credits</div>
          <div class="right">
            <button id="topupBtn">Top up <span id="minTopupBtn">5</span> credits ( £<span id="topupTotal">0</span> )</button>
          </div>
        </div>
        <div style="margin-top:12px;" class="muted">
          By topping up you agree: <span class="warn">we do not charge upfront.</span> We <b>record</b> each top-up and
          <b>invoice weekly</b> for any credits added that week. This will be shown in your ledger below.
        </div>
      </div>

      <div class="card" style="margin-bottom:16px;">
        <div class="row">
          <div style="font-weight:700;">Recent top-ups</div>
          <div class="right"><span class="pill">last 20</span></div>
        </div>
        <table id="topupsTbl">
          <thead><tr><th>When</th><th>Credits</th><th class="right">Charged</th></tr></thead>
          <tbody id="topupsBody"><tr><td colspan="3" class="muted">No top-ups yet</td></tr></tbody>
        </table>
      </div>

      <div class="card">
        <div class="row">
          <div style="font-weight:700;">Recent usage</div>
          <div class="right"><span class="pill">last 20</span></div>
        </div>
        <table id="usageTbl">
          <thead><tr><th>When</th><th>Action</th><th class="right">Credits Δ</th></tr></thead>
        <tbody id="usageBody"><tr><td colspan="3" class="muted">No usage yet</td></tr></tbody>
        </table>
        <div class="muted" style="margin-top:10px;">This page uses an embedded template.</div>
      </div>
    </div>

    <script>
      const pricePer = ${price_per};
      const minTopup = ${min_topup};
      document.getElementById("pricePer").textContent = pricePer.toFixed(2);
      document.getElementById("minTopup").textContent = minTopup;
      document.getElementById("minTopupBtn").textContent = minTopup;
      document.getElementById("topupTotal").textContent = (pricePer * minTopup).toFixed(2);

      async function api(path, opts={}) {
        const res = await fetch(path, {credentials:'include', headers:{'Accept':'application/json','Content-Type':'application/json'}, ...opts});
        if (!res.ok) throw new Error(await res.text());
        return await res.json();
      }

      async function refresh() {
        try {
          const me = await api('/api/me');
          document.getElementById('whoami').textContent = me.email + ' • joined ' + new Date(me.created_at).toLocaleDateString();
          document.getElementById('credits').textContent = me.balance;
          document.getElementById('loginArea').style.display = 'none';
          document.getElementById('logoutBtn').style.display = '';

          const led = await api('/api/ledger?limit=20');
          const topBody = document.getElementById('topupsBody');
          topBody.innerHTML = '';
          if (led.topups.length === 0) topBody.innerHTML = '<tr><td colspan="3" class="muted">No top-ups yet</td></tr>';
          for (const r of led.topups) {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${new Date(r.created_at).toLocaleString()}</td><td>${r.credits}</td><td class="right">£${r.total_price.toFixed(2)}</td>`;
            topBody.appendChild(tr);
          }
          const useBody = document.getElementById('usageBody');
          useBody.innerHTML = '';
          if (led.usage.length === 0) useBody.innerHTML = '<tr><td colspan="3" class="muted">No usage yet</td></tr>';
          for (const r of led.usage) {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${new Date(r.created_at).toLocaleString()}</td><td>${r.note || 'stamp'}</td><td class="right">${r.credits}</td>`;
            useBody.appendChild(tr);
          }
        } catch (e) {
          document.getElementById('whoami').textContent = 'Not logged in';
          document.getElementById('loginArea').style.display = '';
          document.getElementById('logoutBtn').style.display = 'none';
        }
      }

      document.getElementById('loginBtn').onclick = async () => {
        const body = {email:document.getElementById('email').value.trim(), password:document.getElementById('password').value};
        await api('/api/login', {method:'POST', body: JSON.stringify(body)});
        await refresh();
        alert('Logged in.');
      };
      document.getElementById('signupBtn').onclick = async () => {
        const body = {email:document.getElementById('email').value.trim(), password:document.getElementById('password').value};
        await api('/api/signup', {method:'POST', body: JSON.stringify(body)});
        await refresh();
        alert('Account created & logged in.');
      };
      document.getElementById('logoutBtn').onclick = async () => {
        await api('/api/logout', {method:'POST', body:'{}'});
        await refresh();
      };

      document.getElementById('topupBtn').onclick = async () => {
        const ok = confirm(`You are adding ${minTopup} credits.\n\nWe record this and invoice weekly. Unit price £${pricePer.toFixed(2)} (total £${(pricePer*minTopup).toFixed(2)}). Proceed?`);
        if (!ok) return;
        await api('/api/topup', {method:'POST', body: JSON.stringify({credits:minTopup})});
        await refresh();
        alert('Top-up recorded. You will be invoiced in the weekly billing run.');
      };

      refresh();
    </script>
  </body>
</html>
"""

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat() + "Z"}

@app.get("/", response_class=HTMLResponse)
def home():
    return "<div style='padding:24px;font-family:system-ui'>AutoDate service is up. <a href='/billing'>Billing</a></div>"

@app.get("/billing", response_class=HTMLResponse)
def billing():
    html = BILLING_HTML.replace("${price_per}", str(CREDIT_COST_GBP)).replace("${min_topup}", str(MIN_TOPUP))
    return HTMLResponse(html)

# --- Auth API ---
@app.post("/api/signup")
async def signup(payload: dict, request: Request):
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    if not email or not password:
        raise HTTPException(400, "email & password required")
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (email, password_hash, is_admin, created_at) VALUES (?,?,0,?)",
            (email, pw_hash, datetime.utcnow().isoformat()+"Z"),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(400, "email already registered")
    finally:
        conn.close()
    # auto-login
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email=?", (email,))
    uid = cur.fetchone()["id"]
    conn.close()
    request.session["uid"] = uid
    return {"ok": True}

@app.post("/api/login")
async def login(payload: dict, request: Request):
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, password_hash FROM users WHERE email=?", (email,))
    row = cur.fetchone()
    conn.close()
    if not row or not bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
        raise HTTPException(401, "invalid credentials")
    request.session["uid"] = row["id"]
    return {"ok": True}

@app.post("/api/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}

@app.get("/api/me")
def me(request: Request):
    user = require_user(request)
    bal = user_balance(user["id"])
    return {"id": user["id"], "email": user["email"], "is_admin": bool(user["is_admin"]), "created_at": user["created_at"], "balance": bal, "price_per": CREDIT_COST_GBP, "min_topup": MIN_TOPUP}

@app.get("/api/ledger")
def ledger(request: Request, limit: int = 20):
    user = require_user(request)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT created_at, credits, unit_price, total_price, note FROM ledger WHERE user_id=? AND action='topup' ORDER BY id DESC LIMIT ?", (user["id"], limit))
    topups = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT created_at, credits, note FROM ledger WHERE user_id=? AND action='stamp' ORDER BY id DESC LIMIT ?", (user["id"], limit))
    usage = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"topups": topups, "usage": usage}

@app.post("/api/topup")
async def topup(payload: dict, request: Request):
    user = require_user(request)
    credits = int(payload.get("credits") or 0)
    if credits < MIN_TOPUP:
        raise HTTPException(400, f"minimum top-up is {MIN_TOPUP} credits")
    unit = CREDIT_COST_GBP
    total = unit * credits
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ledger (user_id, action, credits, unit_price, total_price, note, created_at) VALUES (?,?,?,?,?,?,?)",
        (user["id"], "topup", credits, unit, total, "Manual billing; weekly invoice", datetime.utcnow().isoformat()+"Z"),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "balance": user_balance(user["id"])}

# --- Minimal stamp endpoint that decrements 1 credit per image successfully processed ---
def _stamp_one(img_bytes: bytes, overlay_text: str, crop_bottom_px: int = 0) -> bytes:
    with Image.open(io.BytesIO(img_bytes)) as im:
        width, height = im.size
        if crop_bottom_px > 0 and crop_bottom_px < height:
            im = im.crop((0, 0, width, height - crop_bottom_px))
        draw = ImageDraw.Draw(im)
        try:
            font = ImageFont.truetype("arial.ttf", 28)
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0,0), overlay_text, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        x = im.width - tw - 10
        y = im.height - th - 10
        draw.text((x, y), overlay_text, font=font, fill="white")
        out = io.BytesIO()
        im.save(out, format="JPEG")
        return out.getvalue()

@app.post("/api/stamp")
async def stamp(
    request: Request,
    files: List[UploadFile] = File(...),
    date_str: str = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(None),
    crop_bottom_px: int = Form(0),
):
    user = require_user(request)
    # compute times
    if not end_time:
        times = [start_time] * len(files)
    else:
        try:
            start_dt = datetime.strptime(start_time, "%H:%M:%S")
            end_dt = datetime.strptime(end_time, "%H:%M:%S")
        except Exception:
            raise HTTPException(400, "time must be HH:MM:SS")
        total = max(1, len(files)-1)
        steps = [(start_dt + i*(end_dt-start_dt)/total).strftime("%H:%M:%S") for i in range(len(files))]
        times = steps

    outputs = []
    used = 0
    for up, t in zip(files, times):
        content = await up.read()
        overlay = f"{date_str} {t}"
        out_bytes = _stamp_one(content, overlay, crop_bottom_px)
        outputs.append(("stamped_"+up.filename, out_bytes))
        used += 1

    # deduct credits (1 per image)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ledger (user_id, action, credits, note, created_at) VALUES (?,?,?,?,?)",
        (user["id"], "stamp", -used, f"Stamped {used} image(s)", datetime.utcnow().isoformat()+"Z"),
    )
    conn.commit()
    conn.close()

    # If single file return image; else ZIP
    if len(outputs) == 1:
        name, data = outputs[0]
        return StreamingResponse(io.BytesIO(data), media_type="image/jpeg", headers={"Content-Disposition": f'attachment; filename="{name}"'})
    else:
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in outputs:
                z.writestr(name, data)
        buf.seek(0)
        return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="stamped_images.zip"'})
