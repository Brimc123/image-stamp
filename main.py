import os
import io
import csv
import random
import sqlite3
from datetime import datetime, timedelta
from string import Template
from typing import List, Optional

from fastapi import FastAPI, Form, UploadFile, File, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, RedirectResponse, PlainTextResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from PIL import Image, ImageDraw, ImageFont

# -------------------------
# Config via environment
# -------------------------
APP_ENV = os.getenv("APP_ENV", "production")
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-me")
ADMIN_CODE = os.getenv("ADMIN_CODE", "change-me-admin")           # private admin-only code
USER_CODE = os.getenv("USER_CODE", "")                             # shared customer code
ADMIN_EMAIL = (os.getenv("ADMIN_EMAIL", "admin@example.com") or "").lower().strip()

ALLOWED_ORIGINS_RAW = os.getenv(
    "ALLOWED_ORIGINS",
    "https://autodate.co.uk,https://www.autodate.co.uk,https://image-stamp.onrender.com"
)
ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGINS_RAW.split(",") if o.strip()]

DB_FILE = os.getenv("DB_FILE", "/var/data/app.db")
DB_PATH = os.getenv("DB_PATH", "dev.db")

CREDIT_COST_GBP = float(os.getenv("CREDIT_COST_GBP", "10"))
MIN_TOPUP_CREDITS = int(os.getenv("MIN_TOPUP", "5"))
FONT_PATH = os.getenv("FONT_PATH", "")
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "imgstamp_session")

BRAND_NAME = os.getenv("BRAND_NAME", "AutoDate")

# -------------------------
# App & middleware
# -------------------------
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax", session_cookie=SESSION_COOKIE_NAME)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# DB helpers
# -------------------------
def _db_path():
    return DB_FILE if DB_FILE.startswith("/") else DB_PATH

def db_conn():
    path = _db_path()
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def _column_exists(cur, table, col):
    cur.execute(f"PRAGMA table_info({table})")
    return any(r["name"] == col for r in cur.fetchall())

def db_init():
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        credits INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS topups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        credits INTEGER NOT NULL,
        amount_gbp REAL NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        credits_delta INTEGER NOT NULL,
        meta TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)

    # ---- schema upgrades (idempotent)
    if not _column_exists(cur, "users", "is_active"):
        cur.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
    if not _column_exists(cur, "users", "suspended_at"):
        cur.execute("ALTER TABLE users ADD COLUMN suspended_at TEXT")
    if not _column_exists(cur, "users", "suspended_reason"):
        cur.execute("ALTER TABLE users ADD COLUMN suspended_reason TEXT")

    conn.commit()
    conn.close()

db_init()

def get_user_by_email(email: str):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email=?", (email,))
    row = cur.fetchone()
    conn.close()
    return row

def ensure_user(email: str):
    u = get_user_by_email(email)
    if u:
        return u
    conn = db_conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute("INSERT INTO users(email, credits, created_at, is_active) VALUES (?,?,?,1)", (email, 0, now))
    conn.commit()
    conn.close()
    return get_user_by_email(email)

def add_topup(user_id: int, credits: int):
    amount = credits * CREDIT_COST_GBP
    conn = db_conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute("INSERT INTO topups(user_id, credits, amount_gbp, created_at) VALUES (?,?,?,?)",
                (user_id, credits, amount, now))
    cur.execute("UPDATE users SET credits = credits + ? WHERE id=?", (credits, user_id))
    cur.execute("INSERT INTO usage(user_id, action, credits_delta, meta, created_at) VALUES (?,?,?,?,?)",
                (user_id, "topup", credits, f"{credits} credits", now))
    conn.commit()
    conn.close()

def add_usage(user_id: int, action: str, credits_delta: int, meta: str = ""):
    conn = db_conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute("INSERT INTO usage(user_id, action, credits_delta, meta, created_at) VALUES (?,?,?,?,?)",
                (user_id, action, credits_delta, meta, now))
    cur.execute("UPDATE users SET credits = credits + ? WHERE id=?", (credits_delta, user_id))
    conn.commit()
    conn.close()

def list_topups(user_id: int):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM topups WHERE user_id=? ORDER BY id DESC LIMIT 20", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def list_usage(user_id: int):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM usage WHERE user_id=? ORDER BY id DESC LIMIT 20", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

# -------------------------
# HTML templates
# -------------------------
login_html = Template(r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Log in · Autodate</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;padding:2rem;background:#0f172a}
.card{max-width:420px;margin:3rem auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:16px;padding:24px;box-shadow:0 10px 30px rgba(2,6,23,.15)}
h1{margin:0 0 12px;font-size:1.6rem;color:#0b1220}
label{display:block;margin:12px 0 6px;color:#0b1220}
input{width:100%;padding:12px;border-radius:10px;border:1px solid #cbd5e1;background:#fff;color:#0b1220}
button{margin-top:16px;width:100%;padding:12px 16px;border:0;border-radius:10px;background:linear-gradient(180deg,#22c55e,#16a34a);color:#061016;font-weight:800;cursor:pointer}
.small{opacity:.8;font-size:.9rem;margin-top:10px;color:#334155}
a{color:#2563eb}
</style>
</head>
<body>
  <div class="card">
    <h1>Sign in</h1>
    <form method="post" action="/login">
      <label>Email</label>
      <input name="email" type="email" placeholder="you@company.com" required />
      <label>Access Code</label>
      <input name="code" type="password" placeholder="••••••••" required />
      <button type="submit">Enter</button>
      <div class="small">Use the access code provided to you.</div>
    </form>
  </div>
</body>
</html>
""")

suspended_html = Template(r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Account Suspended</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;padding:2rem;background:#0b1220}
.card{max-width:560px;margin:3rem auto;background:#111827;border:1px solid #1f2937;border-radius:16px;padding:24px;box-shadow:0 10px 40px rgba(0,0,0,.35);color:#e2e8f0}
h1{margin:0 0 12px;font-size:1.4rem}
.badge{display:inline-block;background:#7c2d12;color:#fff;padding:.2rem .5rem;border-radius:999px;border:1px solid #9a3412}
a{color:#93c5fd}
</style>
</head>
<body>
  <div class="card">
    <h1>Account Suspended</h1>
    <p><span class="badge">Access blocked</span></p>
    <p>Your account is currently suspended. If this is unexpected, please contact the site owner.</p>
    <p><a href="/login">Back to login</a></p>
  </div>
</body>
</html>
""")

billing_html = Template(r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Billing · Autodate</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;padding:2rem;background:linear-gradient(180deg,#0e1530,#0f1b3d);color:#0e1726}
.container{max-width:980px;margin:0 auto}
h1{font-size:2rem;margin:.3rem 0 1rem;color:#e8eefc}
.card{background:rgba(255,255,255,.9);border:1px solid #e5e7eb;border-radius:16px;box-shadow:0 12px 40px rgba(2,6,23,.12)}
.row{display:grid;grid-template-columns:1fr 140px 140px;gap:16px;padding:14px 16px;border-top:1px solid #e5e7eb}
.row.header{color:#475569;background:#f1f5f9;border-radius:16px 16px 0 0;border-top:0}
.badge{display:inline-block;padding:.35rem .7rem;border-radius:999px;background:#eef2ff;color:#3730a3;border:1px solid #c7d2fe}
button{padding:10px 14px;border-radius:10px;border:1px solid #16a34a;background:linear-gradient(180deg,#22c55e,#16a34a);color:#062015;font-weight:800;cursor:pointer}
.small{opacity:.85;color:#dbe2f0}
a{color:#93c5fd}
.flex{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.mt{margin-top:18px}
.note{margin:0 0 12px 0;padding:12px;border-radius:12px;background:#fffbea;border:1px solid #fde68a;color:#92400e}
</style>
</head>
<body>
  <div class="container">
    <a href="/tool2" class="small">← Back to Tool</a>
    <h1>Billing</h1>

    ${note}

    <div class="flex">
      <div class="badge">Credits: ${credits}</div>
      <div class="badge">Price: £${price}/credit</div>
      <div class="badge">Minimum top-up: ${minc} credits (£${minamount})</div>
      <button id="topupBtn">Top up ${minc} credits (£${minamount})</button>
    </div>

    <p class="small mt">
      Top-ups are recorded instantly in your account. <strong>No card is charged on this site.</strong>
      We total your top-ups and <strong>invoice weekly</strong> to the email on file. By proceeding you agree to be billed for the selected top-up.
    </p>

    <h2 class="mt" style="color:#e8eefc">Recent Top-ups</h2>
    <div class="card">
      <div class="row header"><div>When</div><div>Credits</div><div>Charged</div></div>
      ${topups_rows}
    </div>

    <h2 class="mt" style="color:#e8eefc">Recent Usage</h2>
    <div class="card">
      <div class="row header"><div>When</div><div>Action</div><div>Credits Δ</div></div>
      ${usage_rows}
    </div>
  </div>

<script>
document.getElementById('topupBtn').addEventListener('click', async () => {
  const ok = confirm(
    'You are topping up ${minc} credits for £${minamount}.\\n\\n' +
    'These credits will be invoiced weekly. Do you confirm?'
  );
  if(!ok) return;

  const r = await fetch('/api/topup', {method:'POST'});
  const j = await r.json();
  if(j.ok){ alert('Top-up added. New balance: ' + j.credits); location.reload(); }
  else { alert('Top-up failed: ' + (j.error||'unknown')); }
});
</script>
</body>
</html>
""")

# ======= TOOL2 (Preview UI) with logo + Clear button =======
tool2_html = Template(r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>AutoDate · Timestamp Tool</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
:root{
  --bg1:#0f1c3e; --bg2:#0d1834; --grid:#132044;
  --card:#ffffff; --card-soft:#f7f9fc; --text:#0b1220; --muted:#5b6b86;
  --primary:#22c55e; --primary2:#16a34a; --accent:#2563eb; --stroke:#e6eaf2;
}
*{box-sizing:border-box}
body{
  font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
  margin:0;
  background:
    radial-gradient(1200px 640px at 10% -10%, rgba(37,99,235,.35), transparent 60%),
    radial-gradient(900px 520px at 100% 0%, rgba(34,197,94,.18), transparent 65%),
    linear-gradient(180deg,var(--bg1),var(--bg2));
  min-height:100svh;
  color:var(--text);
}
.container{max-width:1150px;margin:0 auto;padding:28px}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px}
.logo{display:flex;align-items:center;gap:12px}
.logo svg{width:44px;height:44px;display:block;filter:drop-shadow(0 6px 16px rgba(37,99,235,.35))}
.nav{display:flex;gap:16px}
.nav a{color:#e7efff;text-underline-offset:3px}
.card{
  position:relative; border-radius:22px; padding:22px; background:var(--card);
  border:1px solid var(--stroke); box-shadow:0 18px 50px rgba(6,11,22,.22);
}
.card.gfx::before{
  content:""; position:absolute; inset:-1px; border-radius:inherit; padding:1px;
  background:linear-gradient(120deg, rgba(37,99,235,.55), rgba(34,197,94,.55));
  -webkit-mask:linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite:xor; mask-composite:exclude; pointer-events:none;
}
.grid{display:grid;grid-template-columns:1.2fr .8fr;gap:20px}
.right .card{position:sticky; top:24px; background:rgba(255,255,255,.95)}
label{display:block;margin:12px 0 6px;color:#364254;font-weight:800;letter-spacing:.2px}
input,select{
  width:100%;padding:12px 14px;border-radius:12px;border:1px solid var(--stroke);
  background:#fff;color:var(--text);outline:none;transition:.15s;
}
input:focus,select:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(37,99,235,.14)}
button{
  padding:12px 16px; border:1px solid var(--primary2);
  background:linear-gradient(180deg,var(--primary),var(--primary2));
  color:#062015;font-weight:900;border-radius:12px;cursor:pointer;
  transition:transform .06s ease, filter .2s ease, box-shadow .2s ease; min-width:158px
}
button:hover{filter:brightness(1.06); box-shadow:0 10px 26px rgba(22,163,74,.36)}
button:active{transform:translateY(1px)}
button.ghost{
  background:#ffffff;border:1px solid var(--stroke);color:#3b4b6a;min-width:auto
}
.small{opacity:.9;color:#64748b}
.drop{
  border:1.5px dashed #c8d3e5;border-radius:14px;padding:22px;background:var(--card-soft);
  display:flex;align-items:center;justify-content:center;min-height:150px;text-align:center;color:#42506a
}
.drop.drag{outline:2px solid #93c5fd}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.hint{font-size:.92rem;color:#6b7a93;margin-top:6px}
.pills{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap}
.pill{padding:6px 10px;border:1px solid var(--stroke);background:#fff;border-radius:999px;cursor:pointer;color:#41506b}
.preview{display:grid;grid-template-columns:repeat(auto-fill, minmax(88px,1fr));gap:10px;margin-top:12px}
.thumb{position:relative;border-radius:12px;overflow:hidden;border:1px solid #dde5f1;background:#f8fbff}
.thumb img{display:block;width:100%;height:88px;object-fit:cover}
.count{margin-left:auto;color:#74829d}
.result-title{margin:0 0 6px 0;color:#1f2937}
.spinner{width:18px;height:18px;border:2px solid #a7f3d0;border-top-color:#065f46;border-radius:50%;display:none; animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@media (max-width: 960px){ .grid{grid-template-columns:1fr} }
</style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="logo" aria-label="AutoDate">
        <!-- Simple logo: calendar + mountain photo + clock tick -->
        <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="AutoDate">
          <defs>
            <linearGradient id="g1" x1="0" x2="1" y1="0" y2="1">
              <stop offset="0" stop-color="#2563eb"/>
              <stop offset="1" stop-color="#22c55e"/>
            </linearGradient>
          </defs>
          <!-- calendar frame -->
          <rect x="6" y="10" rx="8" ry="8" width="40" height="40" fill="#fff" stroke="url(#g1)" stroke-width="2"/>
          <rect x="6" y="10" width="40" height="10" rx="8" ry="8" fill="url(#g1)"/>
          <!-- photo -->
          <rect x="12" y="24" width="28" height="20" rx="4" fill="#eaf2ff" stroke="#cfe0ff"/>
          <path d="M14 40l6-7 5 6 6-8 7 9" fill="none" stroke="#2563eb" stroke-width="2" stroke-linecap="round"/>
          <circle cx="22" cy="30" r="2" fill="#22c55e"/>
          <!-- clock badge -->
          <circle cx="46" cy="46" r="12" fill="#0b1a3a" stroke="url(#g1)" stroke-width="2"/>
          <path d="M46 39v7l5 3" stroke="#a7f3d0" stroke-width="2.5" stroke-linecap="round" fill="none"/>
        </svg>
      </div>
      <div class="nav small">
        <a href="/tool">Classic</a>
        ${admin_link}
        <a href="/billing">Billing</a>
        <a href="/logout">Logout</a>
      </div>
    </div>

    <div class="grid">
      <div class="card gfx">
        <h2 style="margin:0 0 6px 0;color:#0b1220">Timestamp Images</h2>
        <div class="small" style="margin-top:-2px">Randomises time per image if an end time is provided.</div>

        <form id="form" style="margin-top:8px">
          <label>Images <span id="fileCount" class="count">(none)</span></label>
          <input id="fileInput" type="file" name="files" multiple required accept="image/*" hidden />
          <div id="drop" class="drop">
            <div>
              <div style="font-size:28px;line-height:1.1;opacity:.6">⬆️</div>
              Drag & drop images here, or click to choose
            </div>
          </div>
          <div id="previews" class="preview" aria-hidden="true"></div>

          <div class="row2" style="margin-top:12px">
            <div>
              <label>Target date</label>
              <input id="date" type="date" name="date" required />
            </div>
            <div>
              <label>Date format</label>
              <select name="date_format">
                <option value="d_mmm_yyyy">26 Mar 2025, 12:07:36</option>
                <option value="dd_slash_mm_yyyy">01/01/2025, 13:23:30</option>
              </select>
            </div>
          </div>

          <div class="row2">
            <div>
              <label>Start time</label>
              <input id="start" type="time" name="start" step="1" required />
            </div>
            <div>
              <label>End time <span class="small">(optional)</span></label>
              <input id="end" type="time" name="end" step="1" />
            </div>
          </div>

          <label style="margin-top:10px">Crop (px)</label>
          <div class="row2">
            <input name="crop_top" type="number" min="0" step="1" placeholder="top 0" />
            <input id="cropBottom" name="crop_bottom" type="number" min="0" step="1" value="120" />
          </div>
          <div class="pills small">
            Presets:
            <span class="pill" data-crop="0">0</span>
            <span class="pill" data-crop="120">120</span>
            <span class="pill" data-crop="160">160</span>
          </div>
          <div class="hint">Tip: bottom default 120px removes many phone GPS bars. Set to 0 if not needed.</div>

          <div style="display:flex;gap:12px;align-items:center;margin-top:16px;flex-wrap:wrap">
            <button id="goBtn">Process</button>
            <button id="clearBtn" type="button" class="ghost">Clear images</button>
            <div id="spin" class="spinner" aria-hidden="true"></div>
            <span class="small" id="status" aria-live="polite"></span>
          </div>
        </form>
      </div>

      <div class="right">
        <div class="card">
          <h3 class="result-title">Result</h3>
          <div id="result" class="small">You will get a zip download.</div>
        </div>
      </div>
    </div>
  </div>

<script>
const $ = sel => document.querySelector(sel);
const drop = $('#drop');
const input = $('#fileInput');
const previews = $('#previews');
const fileCount = $('#fileCount');
const goBtn = $('#goBtn');
const clearBtn = $('#clearBtn');
const statusEl = $('#status');
const spin = $('#spin');
const resultEl = document.getElementById('result');

function renderPreviews(files){
  previews.innerHTML = '';
  if(!files || !files.length){ fileCount.textContent='(none)'; return; }
  fileCount.textContent = '(' + files.length + (files.length===1?' file':' files') + ')';
  [...files].slice(0,60).forEach(f=>{
    if(!f.type.startsWith('image/')) return;
    const url = URL.createObjectURL(f);
    const card = document.createElement('div');
    card.className='thumb';
    card.innerHTML = '<img src="'+url+'" alt="'+(f.name||"image")+'" />';
    previews.appendChild(card);
    card.querySelector('img').onload = () => URL.revokeObjectURL(url);
  });
}

function clearAll(){
  input.value = "";
  renderPreviews(input.files);
  statusEl.textContent = '';
  resultEl.textContent = 'You will get a zip download.';
}
clearBtn.addEventListener('click', clearAll);

drop.addEventListener('click', ()=> input.click());
['dragenter','dragover'].forEach(ev => drop.addEventListener(ev, e => {e.preventDefault(); drop.classList.add('drag')}))
;['dragleave','drop'].forEach(ev => drop.addEventListener(ev, e => {e.preventDefault(); drop.classList.remove('drag')}))
drop.addEventListener('drop', e => { input.files = e.dataTransfer.files; renderPreviews(input.files); });
input.addEventListener('change', ()=> renderPreviews(input.files));

// Defaults: today & now
(function setDefaults(){
  const now = new Date();
  document.getElementById('date').value = new Date(now.getTime()-now.getTimezoneOffset()*60000).toISOString().slice(0,10);
  const pad = n=>String(n).padStart(2,'0');
  document.getElementById('start').value = pad(now.getHours())+':'+pad(now.getMinutes())+':'+pad(now.getSeconds());
})();

// Crop presets
document.querySelectorAll('.pill').forEach(p=>{
  p.addEventListener('click', ()=> { document.getElementById('cropBottom').value = p.dataset.crop; });
});

document.getElementById('form').addEventListener('submit', async (e) => {
  e.preventDefault();
  if(!input.files || !input.files.length){ alert('Please add at least one image.'); return; }

  const fd = new FormData(e.target);
  [...(input.files||[])].forEach(f => fd.append('files', f));

  goBtn.disabled = true;
  goBtn.textContent = 'Processing…';
  spin.style.display = 'inline-block';
  statusEl.textContent = 'Working on your images…';

  const r = await fetch('/api/stamp', { method:'POST', body: fd });

  if(!r.ok){
    goBtn.disabled = false; goBtn.textContent = 'Process'; spin.style.display = 'none'; statusEl.textContent='';
    if(r.status === 402) { window.location.href = '/billing?nocredits=1'; return; }
    const txt = await r.text().catch(()=> '');
    alert('Failed: ' + r.status + (txt ? ('\\n'+txt) : ''));
    return;
  }

  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'stamped.zip'; a.click();
  URL.revokeObjectURL(url);

  const bal = r.headers.get('X-Credits-Balance');
  resultEl.textContent = 'Downloaded stamped.zip' + (bal?(' — Credits left: '+bal):'');

  goBtn.disabled = false; goBtn.textContent = 'Process'; spin.style.display = 'none'; statusEl.textContent='';
  clearAll(); // auto-clear after download
});
</script>
</body>
</html>
""")

# ======= Admin UI =======
admin_html = Template(r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Admin · ${brand}</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;padding:22px;background:#0b1220;color:#e8eefc}
.wrap{max-width:1100px;margin:0 auto}
h1{margin:.2rem 0 1rem}
.card{background:#0f172a;border:1px solid #1f2a44;border-radius:14px;padding:16px;box-shadow:0 12px 28px rgba(2,6,23,.25)}
.small{opacity:.85}
a{color:#93c5fd}
input{background:#0b1220;border:1px solid #1f2a44;color:#e8eefc;border-radius:10px;padding:8px 10px}
button{padding:8px 12px;border-radius:10px;border:1px solid #16a34a;background:#22c55e;color:#062015;font-weight:800;cursor:pointer}
table{width:100%;border-collapse:collapse}
th,td{padding:8px 10px;border-bottom:1px solid #1f2a44;text-align:left}
th{color:#9fb2d9}
.badge{display:inline-block;padding:.2rem .5rem;border-radius:999px;background:#1f2a44}
.flex{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.reason{width:180px}
label{font-size:.8rem;color:#9fb2d9}
</style>
</head>
<body>
  <div class="wrap">
    <div class="flex" style="justify-content:space-between">
      <h1>${brand} · Admin</h1>
      <div><a href="/tool2">Tool</a> · <a href="/billing">Billing</a> · <a href="/logout">Logout</a></div>
    </div>

    <form method="get" class="card" style="margin-bottom:16px;display:flex;gap:10px;align-items:end;flex-wrap:wrap">
      <div><div class="small">Start</div><input type="date" name="start" value="${start}"></div>
      <div><div class="small">End</div><input type="date" name="end" value="${end}"></div>
      <div><button type="submit">Apply</button></div>
      <div class="small">Exports: <a href="/admin/export/topups.csv?start=${start}&end=${end}">Top-ups CSV</a> · <a href="/admin/export/summary.csv?start=${start}&end=${end}">Summary CSV</a></div>
    </form>

    <div class="card" style="margin-bottom:16px">
      <div class="flex" style="justify-content:space-between">
        <h3 style="margin:0">Users</h3>
        <div class="small">Range: <span class="badge">${start} → ${end}</span></div>
      </div>
      <table style="margin-top:8px">
        <tr>
          <th>Email</th><th>Credits</th><th>Created</th><th>Last login</th>
          <th>Stamp runs</th><th>Top-ups</th><th>Top-up credits</th><th>Top-up £</th>
          <th>Status</th><th>Action</th>
        </tr>
        ${users_rows}
      </table>
    </div>

    <div class="card">
      <h3 style="margin:0 0 8px 0">Recent Top-ups in range</h3>
      <table>
        <tr><th>When</th><th>User</th><th>Credits</th><th>£</th></tr>
        ${topups_rows}
      </table>
    </div>
  </div>
</body>
</html>
""")

# -------------------------
# Utility: auth helpers
# -------------------------
def current_user(request: Request):
    u = request.session.get("user")
    if not u:
        return None
    return u

def require_user(request: Request):
    u = current_user(request)
    if not u:
        return RedirectResponse("/login", status_code=302)
    return u

def require_admin(request: Request):
    u = require_user(request)
    if isinstance(u, RedirectResponse):
        return u
    if not ADMIN_EMAIL or u["email"].lower() != ADMIN_EMAIL:
        return HTMLResponse("<h3>Forbidden</h3><p>Admin only.</p>", status_code=403)
    return u

def require_active_user_row(request: Request):
    """Return sqlite row for the logged-in user; if suspended, clear session and redirect to /suspended."""
    u = current_user(request)
    if not u:
        return RedirectResponse("/login", status_code=302)
    row = get_user_by_email(u["email"])
    if not row or int(row["is_active"] or 0) != 1:
        request.session.clear()
        return RedirectResponse("/suspended", status_code=302)
    return row

# -------------------------
# Routes
# -------------------------
@app.get("/health")
def health():
    return {"ok": True, "db": _db_path(), "env": APP_ENV}

@app.get("/api/ping")
def api_ping():
    return {"ok": True, "time": datetime.utcnow().isoformat()}

@app.get("/__whoami", response_class=PlainTextResponse)
def whoami():
    return "main.py active"

@app.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse("/tool2", status_code=302)

@app.head("/")
def home_head():
    return PlainTextResponse("", status_code=200)

@app.get("/app")
def app_alias():
    return RedirectResponse("/tool2", status_code=302)

# ----- Auth -----
@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    return HTMLResponse(login_html.substitute({}))

@app.post("/login")
async def login_post(request: Request, email: str = Form(...), code: str = Form(...)):
    # Accept either ADMIN_CODE or USER_CODE (if set).
    ok = (code == ADMIN_CODE) or (USER_CODE and code == USER_CODE)
    if not ok:
        return HTMLResponse("<h3>Wrong code</h3><a href='/login'>Back</a>", status_code=401)

    email = email.strip().lower()
    row = ensure_user(email)
    # If suspended, don't start a session.
    if int(row["is_active"] or 0) != 1:
        return RedirectResponse("/suspended", status_code=302)
    try:
        add_usage(row["id"], "login", 0, "signin")
    except Exception as e:
        print("login log failed:", e)
    request.session["user"] = {"email": email}
    return RedirectResponse("/tool2", status_code=302)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

@app.get("/suspended", response_class=HTMLResponse)
def suspended_page():
    return HTMLResponse(suspended_html.substitute({}))

# ----- Billing page -----
@app.get("/billing", response_class=HTMLResponse)
def billing(request: Request):
    row = require_active_user_row(request)
    if isinstance(row, (RedirectResponse, HTMLResponse)):
        return row

    credits = row["credits"]
    tops = list_topups(row["id"])
    use = list_usage(row["id"])

    def fmt_rows(rows, kind):
        if not rows:
            return '<div class="row"><div>No entries yet</div><div>—</div><div>—</div></div>'
        out = []
        for r in rows:
            when = r["created_at"].replace("T"," ").split(".")[0]
            if kind == "topups":
                out.append(f'<div class="row"><div>{when}</div><div>{r["credits"]}</div><div>£{r["amount_gbp"]:.0f}</div></div>')
            else:
                out.append(f'<div class="row"><div>{when}</div><div>{r["action"]}</div><div>{r["credits_delta"]}</div></div>')
        return "\n".join(out)

    note = '<div class="note">You\'re out of credits. Please top up to continue.</div>' if request.query_params.get("nocredits") == "1" else ""

    html = billing_html.substitute(
        note = note,
        credits = credits,
        price = int(CREDIT_COST_GBP),
        minc = MIN_TOPUP_CREDITS,
        minamount = int(MIN_TOPUP_CREDITS*CREDIT_COST_GBP),
        topups_rows = fmt_rows(tops, "topups"),
        usage_rows = fmt_rows(use, "usage")
    )
    return HTMLResponse(html)

@app.post("/api/topup")
def api_topup(request: Request):
    row = require_active_user_row(request)
    if isinstance(row, (RedirectResponse, HTMLResponse)):
        return JSONResponse({"ok": False, "error": "not_active"}, status_code=403)
    add_topup(row["id"], MIN_TOPUP_CREDITS)
    refreshed = get_user_by_email(row["email"])
    return {"ok": True, "credits": refreshed["credits"]}

# ----- Tool pages -----
@app.get("/tool")
def tool_redirect():
    return RedirectResponse("/tool2", status_code=302)

@app.get("/tool2", response_class=HTMLResponse)
def tool2(request: Request):
    row = require_active_user_row(request)
    if isinstance(row, (RedirectResponse, HTMLResponse)):
        return row
    show_admin = ADMIN_EMAIL and row["email"].lower() == ADMIN_EMAIL
    admin_link = '<a href="/admin">Admin</a>' if show_admin else ''
    admin_link = (admin_link + ' ') if admin_link else ''
    return HTMLResponse(tool2_html.safe_substitute(admin_link=admin_link))

# ----- Admin dashboard & exports -----
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, start: Optional[str] = None, end: Optional[str] = None):
    u = require_admin(request)
    if isinstance(u, (RedirectResponse, HTMLResponse)):
        return u

    today = datetime.utcnow().date()
    if not start:
        start = (today - timedelta(days=6)).isoformat()
    if not end:
        end = today.isoformat()

    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end) + timedelta(days=1)

    conn = db_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
          u.id, u.email, u.credits, u.created_at, u.is_active, u.suspended_at, u.suspended_reason,
          (SELECT MAX(created_at) FROM usage WHERE user_id=u.id AND action='login') AS last_login,
          (SELECT COUNT(*) FROM usage WHERE user_id=u.id AND action='stamp' AND created_at>=? AND created_at<?) AS stamp_runs,
          (SELECT COUNT(*) FROM topups WHERE user_id=u.id AND created_at>=? AND created_at<?) AS topup_count,
          (SELECT COALESCE(SUM(credits),0) FROM topups WHERE user_id=u.id AND created_at>=? AND created_at<?) AS topup_credits,
          (SELECT COALESCE(SUM(amount_gbp),0) FROM topups WHERE user_id=u.id AND created_at>=? AND created_at<?) AS topup_amount
        FROM users u
        ORDER BY u.id DESC
    """, (start_dt.isoformat(), end_dt.isoformat(),
          start_dt.isoformat(), end_dt.isoformat(),
          start_dt.isoformat(), end_dt.isoformat(),
          start_dt.isoformat(), end_dt.isoformat()))
    users = cur.fetchall()

    cur.execute("""
        SELECT t.created_at, u.email, t.credits, t.amount_gbp
        FROM topups t JOIN users u ON u.id=t.user_id
        WHERE t.created_at>=? AND t.created_at<?
        ORDER BY t.created_at DESC
        LIMIT 200
    """, (start_dt.isoformat(), end_dt.isoformat()))
    tops = cur.fetchall()
    conn.close()

    def fmt(dt):
        return (dt or "").replace("T"," ").split(".")[0] if dt else "—"

    users_rows = ""
    for r in users:
        status = "Active" if int(r["is_active"] or 0) == 1 else f"Suspended<br><span class='small'>{fmt(r['suspended_at'])}</span><br><span class='small'>{(r['suspended_reason'] or '')}</span>"
        if ADMIN_EMAIL and r["email"].lower() == ADMIN_EMAIL:
            action = "<span class='small'>—</span>"
        elif int(r["is_active"] or 0) == 1:
            action = (
                "<form method='post' action='/admin/user/suspend' class='flex'>"
                f"<input type='hidden' name='email' value='{r['email']}'>"
                "<label>Reason</label><input name='reason' class='reason' placeholder='e.g. unpaid invoice'/>"
                "<button> Suspend </button>"
                "</form>"
            )
        else:
            action = (
                "<form method='post' action='/admin/user/unsuspend' class='flex'>"
                f"<input type='hidden' name='email' value='{r['email']}'>"
                "<button> Reinstate </button>"
                "</form>"
            )

        users_rows += (
            f"<tr>"
            f"<td>{r['email']}</td>"
            f"<td>{r['credits']}</td>"
            f"<td>{fmt(r['created_at'])}</td>"
            f"<td>{fmt(r['last_login'])}</td>"
            f"<td>{r['stamp_runs']}</td>"
            f"<td>{r['topup_count']}</td>"
            f"<td>{r['topup_credits']}</td>"
            f"<td>£{r['topup_amount']:.0f}</td>"
            f"<td>{status}</td>"
            f"<td>{action}</td>"
            f"</tr>"
        )

    if not users_rows:
        users_rows = "<tr><td colspan=10>No users yet</td></tr>"

    topups_rows = ""
    for t in tops:
        topups_rows += f"<tr><td>{fmt(t['created_at'])}</td><td>{t['email']}</td><td>{t['credits']}</td><td>£{t['amount_gbp']:.0f}</td></tr>"
    if not topups_rows:
        topups_rows = "<tr><td colspan=4>No top-ups in range</td></tr>"

    html = admin_html.substitute(
        brand=BRAND_NAME,
        start=start,
        end=end,
        users_rows=users_rows,
        topups_rows=topups_rows
    )
    return HTMLResponse(html)

@app.post("/admin/user/suspend")
def admin_suspend_user(request: Request, email: str = Form(...), reason: str = Form("")):
    u = require_admin(request)
    if isinstance(u, (RedirectResponse, HTMLResponse)):
        return u
    if ADMIN_EMAIL and email.lower() == ADMIN_EMAIL:
        return HTMLResponse("<h3>Cannot suspend admin account.</h3><p><a href='/admin'>Back</a></p>", status_code=400)

    conn = db_conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute("UPDATE users SET is_active=0, suspended_at=?, suspended_reason=? WHERE email=?", (now, reason.strip(), email.lower()))
    conn.commit()
    conn.close()
    return RedirectResponse("/admin", status_code=302)

@app.post("/admin/user/unsuspend")
def admin_unsuspend_user(request: Request, email: str = Form(...)):
    u = require_admin(request)
    if isinstance(u, (RedirectResponse, HTMLResponse)):
        return u
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_active=1, suspended_at=NULL, suspended_reason=NULL WHERE email=?", (email.lower(),))
    conn.commit()
    conn.close()
    return RedirectResponse("/admin", status_code=302)

@app.get("/admin/export/topups.csv")
def export_topups_csv(request: Request, start: str, end: str):
    u = require_admin(request)
    if isinstance(u, (RedirectResponse, HTMLResponse)):
        return u

    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end) + timedelta(days=1)

    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT t.created_at, u.email, t.credits, t.amount_gbp
        FROM topups t JOIN users u ON u.id=t.user_id
        WHERE t.created_at>=? AND t.created_at<?
        ORDER BY t.created_at ASC
    """, (start_dt.isoformat(), end_dt.isoformat()))
    rows = cur.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["when_utc", "email", "credits", "amount_gbp"])
    for r in rows:
        writer.writerow([r["created_at"], r["email"], r["credits"], f"{r['amount_gbp']:.2f}"])
    data = output.getvalue().encode("utf-8")
    headers = {
        "Content-Disposition": f'attachment; filename="topups_{start}_to_{end}.csv"'
    }
    return Response(content=data, media_type="text/csv; charset=utf-8", headers=headers)

@app.get("/admin/export/summary.csv")
def export_summary_csv(request: Request, start: str, end: str):
    u = require_admin(request)
    if isinstance(u, (RedirectResponse, HTMLResponse)):
        return u

    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end) + timedelta(days=1)

    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT
          u.email, u.credits AS current_credits,
          (SELECT COUNT(*) FROM topups WHERE user_id=u.id AND created_at>=? AND created_at<?) AS topup_count,
          (SELECT COALESCE(SUM(credits),0) FROM topups WHERE user_id=u.id AND created_at>=? AND created_at<?) AS topup_credits,
          (SELECT COALESCE(SUM(amount_gbp),0) FROM topups WHERE user_id=u.id AND created_at>=? AND created_at<?) AS topup_amount,
          (SELECT COUNT(*) FROM usage WHERE user_id=u.id AND action='stamp' AND created_at>=? AND created_at<?) AS stamp_runs,
          (SELECT COALESCE(SUM(-credits_delta),0) FROM usage WHERE user_id=u.id AND action='stamp' AND created_at>=? AND created_at<?) AS credits_used
        FROM users u
        ORDER BY u.email ASC
    """, (start_dt.isoformat(), end_dt.isoformat(),
          start_dt.isoformat(), end_dt.isoformat(),
          start_dt.isoformat(), end_dt.isoformat(),
          start_dt.isoformat(), end_dt.isoformat(),
          start_dt.isoformat(), end_dt.isoformat()))
    rows = cur.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["email","topup_count","topup_credits","topup_amount_gbp","stamp_runs","credits_used","current_credits"])
    for r in rows:
        writer.writerow([
            r["email"], r["topup_count"], r["topup_credits"],
            f"{r['topup_amount']:.2f}", r["stamp_runs"], r["credits_used"], r["current_credits"]
        ])
    data = output.getvalue().encode("utf-8")
    headers = {
        "Content-Disposition": f'attachment; filename="summary_{start}_to_{end}.csv"'
    }
    return Response(content=data, media_type="text/csv; charset=utf-8", headers=headers)

# -------------------------
# Image stamping
# -------------------------
def load_font(size: int):
    candidates = []
    if FONT_PATH:
        candidates.append(FONT_PATH)
    candidates += [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf"
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size=size)
        except Exception:
            continue
    return ImageFont.load_default()

def draw_timestamp(img: Image.Image, text: str) -> Image.Image:
    im = img.convert("RGBA")
    draw = ImageDraw.Draw(im)
    w, h = im.size
    font_size = max(18, int(w * 0.032))
    font = load_font(font_size)
    tw, th = draw.textbbox((0,0), text, font=font)[2:]
    pad = int(font_size * 0.4)
    x = w - tw - pad
    y = h - th - pad
    for ox in (-1,0,1):
        for oy in (-1,0,1):
            if ox==0 and oy==0: continue
            draw.text((x+ox, y+oy), text, font=font, fill=(0,0,0,255))
    draw.text((x, y), text, font=font, fill=(255,255,255,255))
    return im.convert("RGB")

def fmt_datetime(dt: datetime, fmt_key: str) -> str:
    if fmt_key == "dd_slash_mm_yyyy":
        return dt.strftime("%d/%m/%Y, %H:%M:%S")
    return dt.strftime("%d %b %Y, %H:%M:%S")

@app.post("/api/stamp")
async def api_stamp(
    request: Request,
    files: List[UploadFile] = File(...),
    date: str = Form(...),
    start: str = Form(...),
    end: Optional[str] = Form(None),
    crop_top: Optional[int] = Form(0),
    crop_bottom: Optional[int] = Form(0),
    date_format: Optional[str] = Form("d_mmm_yyyy"),
):
    row = require_active_user_row(request)
    if isinstance(row, (RedirectResponse, HTMLResponse)):
        return JSONResponse({"ok": False, "error": "not_active"}, status_code=403)

    if row["credits"] <= 0:
        return JSONResponse({"ok": False, "error": "no_credits"}, status_code=402)

    base_date = datetime.strptime(date, "%Y-%m-%d").date()
    start_t = datetime.strptime(start, "%H:%M:%S").time()
    end_t = datetime.strptime(end, "%H:%M:%S").time() if end else start_t
    start_dt = datetime.combine(base_date, start_t)
    end_dt = datetime.combine(base_date, end_t)
    if end_dt < start_dt:
        end_dt = start_dt

    import zipfile, tempfile, os as _os
    tmp = tempfile.TemporaryDirectory()
    zip_path = _os.path.join(tmp.name, "stamped.zip")
    zf = zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED)

    n = len(files)
    for i, f in enumerate(files):
        raw = await f.read()
        img = Image.open(io.BytesIO(raw)).convert("RGB")

        ct = int(crop_top or 0)
        cb = int(crop_bottom or 0)
        w, h = img.size
        top = max(0, ct)
        bottom = max(0, cb)
        if top or bottom:
            img = img.crop((0, top, w, max(top, h-bottom)))

        if n == 1 or start_dt == end_dt:
            dt = start_dt
        else:
            delta = (end_dt - start_dt).total_seconds()
            r = random.random()
            dt = start_dt + timedelta(seconds=int(r * delta))

        text = fmt_datetime(dt, date_format)
        stamped = draw_timestamp(img, text)

        name = f.filename or f"image_{i+1}.jpg"
        buf = io.BytesIO()
        stamped.save(buf, format="JPEG", quality=92)
        zf.writestr(name.replace(".jpeg",".jpg"), buf.getvalue())

    zf.close()
    # deduct 1 credit per run
    add_usage(row["id"], "stamp", -1, f"{n} image(s)")
    new_row = get_user_by_email(row["email"])

    def iterfile():
        with open(zip_path, "rb") as f:
            yield from f
        tmp.cleanup()

    headers = {
        "Content-Disposition": 'attachment; filename="stamped.zip"',
        "X-Credits-Balance": str(new_row["credits"])
    }
    return StreamingResponse(iterfile(), media_type="application/zip", headers=headers)
