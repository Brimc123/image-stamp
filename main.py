import os
import io
import random
import sqlite3
from datetime import datetime, timedelta
from string import Template
from typing import List, Optional

from fastapi import FastAPI, Form, UploadFile, File, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, RedirectResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from PIL import Image, ImageDraw, ImageFont

# -------------------------
# Config via environment
# -------------------------
APP_ENV = os.getenv("APP_ENV", "production")
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-me")
ADMIN_CODE = os.getenv("ADMIN_CODE", "change-me")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
ALLOWED_ORIGINS_RAW = os.getenv("ALLOWED_ORIGINS", "https://autodate.co.uk,https://www.autodate.co.uk,https://image-stamp.onrender.com")
ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGINS_RAW.split(",") if o.strip()]
DB_FILE = os.getenv("DB_FILE", "/var/data/app.db")  # Render persistent disk path if mounted, else fallback file
DB_PATH = os.getenv("DB_PATH", "dev.db")            # ignored when DB_FILE is absolute
CREDIT_COST_GBP = float(os.getenv("CREDIT_COST_GBP", "10"))
MIN_TOPUP_CREDITS = int(os.getenv("MIN_TOPUP", "5"))

# Optional custom font in repo (put e.g. fonts/Roboto-Regular.ttf)
FONT_PATH = os.getenv("FONT_PATH", "")  # leave empty to use system DejaVuSans
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "imgstamp_session")

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
    os.makedirs(os.path.dirname(path), exist_ok=True) if "/" in path else None
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

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
    cur.execute("INSERT INTO users(email, credits, created_at) VALUES (?,?,?)", (email, 0, now))
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
# HTML (string.Template – no {{ }} so Python won’t choke)
# -------------------------
login_html = Template(r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Log in · Autodate</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;padding:2rem;background:#0f172a;color:#e2e8f0}
.card{max-width:420px;margin:3rem auto;background:#111827;border:1px solid #1f2937;border-radius:16px;padding:24px;box-shadow:0 10px 30px rgba(0,0,0,.35)}
h1{margin:0 0 12px;font-size:1.5rem;color:#fff}
label{display:block;margin:12px 0 6px}
input{width:100%;padding:12px;border-radius:10px;border:1px solid #374151;background:#0b1220;color:#e5e7eb}
button{margin-top:16px;width:100%;padding:12px 16px;border:0;border-radius:10px;background:#22c55e;color:#0b1220;font-weight:700;cursor:pointer}
.small{opacity:.8;font-size:.9rem;margin-top:10px}
a{color:#93c5fd}
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

billing_html = Template(r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Billing · Autodate</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;padding:2rem;background:#0f172a;color:#e2e8f0}
.container{max-width:980px;margin:0 auto}
h1{font-size:2rem;margin:.3rem 0 1rem}
.card{background:#111827;border:1px solid #1f2937;border-radius:16px;box-shadow:0 10px 30px rgba(0,0,0,.35)}
.row{display:grid;grid-template-columns:1fr 140px 140px;gap:16px;padding:14px 16px;border-top:1px solid #1f2937}
.row.header{color:#94a3b8;background:#0b1220;border-radius:16px 16px 0 0;border-top:0}
.badge{display:inline-block;padding:.25rem .5rem;border-radius:999px;background:#1f2937;color:#cbd5e1}
button{padding:10px 14px;border-radius:10px;border:1px solid #16a34a;background:#22c55e;color:#0b1220;font-weight:800;cursor:pointer}
.small{opacity:.8}
a{color:#93c5fd}
.flex{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.mt{margin-top:18px}
.note{margin:0 0 12px 0;padding:12px;border-radius:12px;background:#1f2937;border:1px solid #334155}
</style>
</head>
<body>
  <div class="container">
    <a href="/tool" class="small">← Back to Image Tool</a>
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

    <h2 class="mt">Recent Top-ups</h2>
    <div class="card">
      <div class="row header"><div>When</div><div>Credits</div><div>Charged</div></div>
      ${topups_rows}
    </div>

    <h2 class="mt">Recent Usage</h2>
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

tool_html = Template(r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Image Timestamp Tool · Autodate</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;padding:2rem;background:#0f172a;color:#e2e8f0}
.container{max-width:980px;margin:0 auto}
h1{font-size:2rem;margin:.3rem 0 1rem}
.card{background:#111827;border:1px solid #1f2937;border-radius:16px;box-shadow:0 10px 30px rgba(0,0,0,.35);padding:16px}
label{display:block;margin:10px 0 6px}
input,select{width:100%;padding:10px;border-radius:10px;border:1px solid #374151;background:#0b1220;color:#e5e7eb}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
button{margin-top:16px;padding:12px 16px;border:0;border-radius:10px;background:#22c55e;color:#0b1220;font-weight:700;cursor:pointer}
a{color:#93c5fd}
.small{opacity:.8}
</style>
</head>
<body>
  <div class="container">
    <div class="grid">
      <div>
        <a href="/billing" class="small">← Billing</a>
        <h1>Image Timestamp Tool</h1>
        <form id="form">
          <label>Images (one or many)</label>
          <input type="file" name="files" multiple required accept="image/*" />

          <label>Target date</label>
          <input type="date" name="date" required />

          <label>Start time</label>
          <input type="time" name="start" step="1" required />

          <label>End time (for multiple images; optional)</label>
          <input type="time" name="end" step="1" />

          <label>Crop (pixels from each edge, e.g. to remove top GPS bar)</label>
          <div class="grid">
            <input name="crop_top" type="number" min="0" step="1" placeholder="top 0" />
            <input name="crop_bottom" type="number" min="0" step="1" placeholder="bottom 0" />
          </div>

          <label>Date format (match your originals)</label>
          <select name="date_format">
            <option value="d_mmm_yyyy">26 Mar 2025, 12:07:36</option>
            <option value="dd_slash_mm_yyyy">01/01/2025, 13:23:30</option>
          </select>

          <button>Process</button>
        </form>
        <p class="small">Each run deducts 1 credit from your balance.</p>
      </div>
      <div class="card">
        <h3>Result</h3>
        <div id="result" class="small">You will get a zip download.</div>
      </div>
    </div>
  </div>

<script>
document.getElementById('form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const r = await fetch('/api/stamp', { method:'POST', body: fd });

  if(!r.ok){
    // Friendly redirect when out of credits
    if(r.status === 402) { window.location.href = '/billing?nocredits=1'; return; }
    alert('Failed: ' + r.status);
    return;
  }

  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'stamped.zip'; a.click();
  URL.revokeObjectURL(url);
  document.getElementById('result').textContent = 'Downloaded stamped.zip';
});
</script>
</body>
</html>
""")

# -------------------------
# Utility: auth
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

# -------------------------
# Routes
# -------------------------
@app.get("/health")
def health():
    return {"ok": True, "db": _db_path(), "env": APP_ENV}

# Debug helper so you can check quickly in the browser
@app.get("/__whoami", response_class=PlainTextResponse)
def whoami():
    return "main.py active"

@app.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse("/tool", status_code=302)

# Alias so /app works (old link)
@app.get("/app")
def app_alias():
    return RedirectResponse("/tool", status_code=302)

# ----- Auth -----
@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    return HTMLResponse(login_html.substitute({}))

@app.post("/login")
async def login_post(request: Request, email: str = Form(...), code: str = Form(...)):
    if code != ADMIN_CODE:
        return HTMLResponse("<h3>Wrong code</h3><a href='/login'>Back</a>", status_code=401)
    ensure_user(email.strip().lower())
    request.session["user"] = {"email": email.strip().lower()}
    return RedirectResponse("/tool", status_code=302)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

# ----- Billing page (no Stripe, just records top-ups) -----
@app.get("/billing", response_class=HTMLResponse)
def billing(request: Request):
    u = current_user(request)
    if not u:
        return RedirectResponse("/login", status_code=302)

    user_row = get_user_by_email(u["email"])
    credits = user_row["credits"] if user_row else 0
    tops = list_topups(user_row["id"]) if user_row else []
    use = list_usage(user_row["id"]) if user_row else []

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
    u = current_user(request)
    if not u:
        return JSONResponse({"ok": False, "error": "not_signed_in"}, status_code=401)
    row = ensure_user(u["email"])
    add_topup(row["id"], MIN_TOPUP_CREDITS)
    refreshed = get_user_by_email(u["email"])
    return {"ok": True, "credits": refreshed["credits"]}

# ----- Tool page -----
@app.get("/tool", response_class=HTMLResponse)
def tool(request: Request):
    u = current_user(request)
    if not u:
        return RedirectResponse("/login", status_code=302)
    return HTMLResponse(tool_html.substitute({}))

# -------------------------
# Image stamping
# -------------------------
def load_font(size: int):
    # fallbacks if custom path not set
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

    # relative sizing by width
    w, h = im.size
    font_size = max(18, int(w * 0.032))  # ~3.2% of width; tweak to taste
    font = load_font(font_size)

    # measure
    tw, th = draw.textbbox((0,0), text, font=font)[2:]
    pad = int(font_size * 0.4)
    x = w - tw - pad
    y = h - th - pad

    # outline (black stroke for readability)
    for ox in (-1,0,1):
        for oy in (-1,0,1):
            if ox==0 and oy==0: continue
            draw.text((x+ox, y+oy), text, font=font, fill=(0,0,0,255))
    # text fill (white)
    draw.text((x, y), text, font=font, fill=(255,255,255,255))
    return im.convert("RGB")

def fmt_datetime(dt: datetime, fmt_key: str) -> str:
    if fmt_key == "dd_slash_mm_yyyy":
        return dt.strftime("%d/%m/%Y, %H:%M:%S")
    # default like “26 Mar 2025, 12:07:36”
    return dt.strftime("%d %b %Y, %H:%M:%S")

@app.post("/api/stamp")
async def api_stamp(
    request: Request,
    files: List[UploadFile] = File(...),
    date: str = Form(...),          # "2025-03-26"
    start: str = Form(...),         # "12:07:36"
    end: Optional[str] = Form(None),# "13:23:30"
    crop_top: Optional[int] = Form(0),
    crop_bottom: Optional[int] = Form(0),
    date_format: Optional[str] = Form("d_mmm_yyyy"),
):
    u = current_user(request)
    if not u:
        return JSONResponse({"ok": False, "error": "not_signed_in"}, status_code=401)

    # check credits (1 credit per run)
    row = ensure_user(u["email"])
    if row["credits"] <= 0:
        # client JS will redirect to /billing?nocredits=1 when it sees 402
        return JSONResponse({"ok": False, "error": "no_credits"}, status_code=402)

    # parse times
    base_date = datetime.strptime(date, "%Y-%m-%d").date()
    start_t = datetime.strptime(start, "%H:%M:%S").time()
    end_t = datetime.strptime(end, "%H:%M:%S").time() if end else start_t
    start_dt = datetime.combine(base_date, start_t)
    end_dt = datetime.combine(base_date, end_t)
    if end_dt < start_dt:
        end_dt = start_dt

    # process
    import zipfile, tempfile, os as _os
    tmp = tempfile.TemporaryDirectory()
    zip_path = _os.path.join(tmp.name, "stamped.zip")
    zf = zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED)

    n = len(files)
    for i, f in enumerate(files):
        raw = await f.read()
        img = Image.open(io.BytesIO(raw)).convert("RGB")

        # crop if asked (remove fixed bars e.g. top GPS stripe)
        ct = int(crop_top or 0)
        cb = int(crop_bottom or 0)
        w, h = img.size
        top = max(0, ct)
        bottom = max(0, cb)
        if top or bottom:
            img = img.crop((0, top, w, max(top, h-bottom)))

        # choose timestamp for this image
        if n == 1 or start_dt == end_dt:
            dt = start_dt
        else:
            delta = (end_dt - start_dt).total_seconds()
            r = random.random()
            dt = start_dt + timedelta(seconds=int(r * delta))

        text = fmt_datetime(dt, date_format)
        stamped = draw_timestamp(img, text)

        # write to zip
        name = f.filename or f"image_{i+1}.jpg"
        buf = io.BytesIO()
        stamped.save(buf, format="JPEG", quality=92)
        zf.writestr(name.replace(".jpeg",".jpg"), buf.getvalue())

    zf.close()

    # deduct 1 credit per run
    add_usage(row["id"], "stamp", -1, f"{n} image(s)")
    new_row = get_user_by_email(u["email"])

    # stream the zip
    def iterfile():
        with open(zip_path, "rb") as f:
            yield from f
        tmp.cleanup()

    headers = {
        "Content-Disposition": 'attachment; filename="stamped.zip"',
        "X-Credits-Balance": str(new_row["credits"])
    }
    return StreamingResponse(iterfile(), media_type="application/zip", headers=headers)
