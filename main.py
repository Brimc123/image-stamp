# main.py — Image Timestamp Tool with Login + Stripe top-ups + polished UI
# ---------------------------------------------------------------
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.status import HTTP_302_FOUND
from typing import List, Optional, Tuple
from datetime import datetime, timedelta
from email_validator import validate_email, EmailNotValidError
import random, io, os, json, zipfile, sqlite3, bcrypt, stripe
from PIL import Image, ImageDraw, ImageFont

# ---------- Config ----------
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-me")
ADMIN_CODE = os.getenv("ADMIN_CODE")  # optional
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID")  # £10 per credit
stripe.api_key = STRIPE_SECRET_KEY

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "app.db")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

# ---------- DB ----------
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT UNIQUE NOT NULL,
      password_hash BLOB NOT NULL,
      credits INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS payments (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      session_id TEXT UNIQUE NOT NULL,
      credits INTEGER NOT NULL,
      amount INTEGER NOT NULL,
      currency TEXT NOT NULL,
      status TEXT NOT NULL,
      created_at TEXT NOT NULL,
      FOREIGN KEY (user_id) REFERENCES users(id)
    )""")
    conn.commit()
    conn.close()

@app.on_event("startup")
def _startup():
    init_db()

# ---------- Auth helpers ----------
def hash_password(pw: str) -> bytes:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt())

def check_password(pw: str, pwd_hash: bytes) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), pwd_hash)
    except Exception:
        return False

def get_user_by_id(uid: int) -> Optional[sqlite3.Row]:
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (uid,))
    row = cur.fetchone()
    conn.close()
    return row

def get_user_by_email(email: str) -> Optional[sqlite3.Row]:
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cur.fetchone()
    conn.close()
    return row

def create_user(email: str, password: str) -> int:
    conn = db(); cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (email, password_hash, credits, created_at) VALUES (?, ?, 0, ?)",
        (email, hash_password(password), datetime.utcnow().isoformat())
    )
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    return uid

def add_credits(user_id: int, n: int) -> int:
    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE users SET credits = credits + ? WHERE id = ?", (int(n), user_id))
    conn.commit()
    cur.execute("SELECT credits FROM users WHERE id = ?", (user_id,))
    bal = cur.fetchone()["credits"]
    conn.close()
    return bal

def spend_credit(user_id: int) -> int:
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT credits FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    if not row or row["credits"] < 1:
        conn.close()
        raise HTTPException(status_code=402, detail="Not enough credits. Please top up.")
    cur.execute("UPDATE users SET credits = credits - 1 WHERE id = ?", (user_id,))
    conn.commit()
    cur.execute("SELECT credits FROM users WHERE id = ?", (user_id,))
    bal = cur.fetchone()["credits"]
    conn.close()
    return bal

def require_user(request: Request) -> sqlite3.Row:
    uid = request.session.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="Login required")
    user = get_user_by_id(uid)
    if not user:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Login required")
    return user

# ---------- Health ----------
@app.get("/api/ping")
def ping():
    return {"ok": True, "message": "pong"}

@app.get("/health")
def health():
    return {"ok": True}

# ---------- Fonts + stamp ----------
def _load_font(size: int = 30) -> ImageFont.FreeTypeFont:
    for candidate in ["arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()

def _draw_text_with_outline(draw: ImageDraw.ImageDraw, xy, text, font):
    x, y = xy
    for dx in (-1,0,1):
        for dy in (-1,0,1):
            if dx or dy:
                draw.text((x+dx, y+dy), text, font=font, fill="black")
    draw.text((x,y), text, font=font, fill="white")

def _stamp_image(binary: bytes, text: str, crop_bottom_px: int) -> bytes:
    with Image.open(io.BytesIO(binary)) as img:
        img = img.convert("RGB")
        w, h = img.size
        crop_bottom_px = max(0, min(int(crop_bottom_px), h-1))
        if crop_bottom_px:
            img = img.crop((0,0,w,h - crop_bottom_px))
        draw = ImageDraw.Draw(img)
        font = _load_font(30)
        bbox = draw.textbbox((0,0), text, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        x, y = img.size[0]-tw-12, img.size[1]-th-12
        _draw_text_with_outline(draw, (x,y), text, font)
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=90, optimize=True)
        out.seek(0)
        return out.read()

def _parse_time_str(t: str) -> datetime:
    fmt = "%H:%M:%S" if t and t.count(":") == 2 else "%H:%M"
    return datetime.strptime(t, fmt)

# ---------- HTML (string.Template-friendly) ----------
BASE_CSS = """
:root{--brand:#6b46c1;--accent:#0ea5e9;}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;background:#f8fafc;color:#0f172a}
.container{max-width:960px;margin:0 auto;padding:24px}
.header{background:#ffffff;border-bottom:1px solid #eaeaea}
.header .bar{display:flex;justify-content:space-between;align-items:center;padding:16px 24px}
.brand{font-weight:800;font-size:20px;color:#0f172a;text-decoration:none}
.nav a{color:#334155;text-decoration:none;margin-left:16px}
.card{background:#fff;border:1px solid #eaeaea;border-radius:14px;padding:18px;margin:16px 0;box-shadow:0 1px 2px rgba(0,0,0,.03)}
.btn{background:var(--accent);color:#fff;padding:10px 14px;border:none;border-radius:10px;cursor:pointer}
.btn.secondary{background:var(--brand)}
input,select{padding:10px;border:1px solid #e2e8f0;border-radius:10px;width:100%}
label{font-weight:600}
.row{display:flex;gap:12px;flex-wrap:wrap}
.col{flex:1}
.muted{color:#64748b}
a.link{color:var(--brand);text-decoration:none}
"""

def shell(html_body: str, user: Optional[sqlite3.Row]) -> str:
    auth_links = """
      <a class="link" href="/login">Log in</a>
      <a class="link" href="/register">Register</a>
    """ if not user else f"""
      <span class="muted">Signed in as {user['email']}</span>
      <a class="link" href="/billing">Billing</a>
      <a class="link" href="/logout">Log out</a>
    """
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>AutoDate</title>
<style>{BASE_CSS}</style></head>
<body>
  <header class="header">
    <div class="bar">
      <a class="brand" href="/">AutoDate</a>
      <nav class="nav">{auth_links}</nav>
    </div>
  </header>
  <div class="container">{html_body}</div>
</body></html>"""

def home_html(user: Optional[sqlite3.Row]) -> str:
    credits = user["credits"] if user else 0
    body = f"""
    <div class="card">
      <h1>Image Timestamp Tool</h1>
      <p class="muted">Stamp a custom date + time onto one or more images, optionally cropping from the bottom.</p>
      <div class="row">
        <a class="link" href="/tool">Open the tool →</a>
        <a class="link" href="/billing">Billing</a>
      </div>
      <p class="muted">{"Credits available: <strong>"+str(credits)+"</strong>" if user else "Please log in to use the tool."}</p>
    </div>
    """
    return shell(body, user)

def auth_form(title: str, action: str, extra: str = "", error: str = "") -> str:
    err = f'<p class="muted" style="color:#b91c1c">{error}</p>' if error else ""
    body = f"""
    <div class="card">
      <h1>{title}</h1>
      {err}
      <form method="post" action="{action}" class="row">
        <div class="col">
          <label>Email</label>
          <input name="email" type="email" required placeholder="you@example.com" />
        </div>
        <div class="col">
          <label>Password</label>
          <input name="password" type="password" required placeholder="••••••••" />
        </div>
        {extra}
        <div>
          <button class="btn" type="submit">{title}</button>
        </div>
      </form>
    </div>
    """
    return shell(body, None)

def billing_html(user: sqlite3.Row, flash: str = "") -> str:
    msg = f'<p class="muted" style="color:#065f46">{flash}</p>' if flash else ""
    body = f"""
    <div class="card">
      <h1>Billing</h1>
      <p>Credits: <strong>{user['credits']}</strong> &middot; Price: £10 per credit</p>
      {msg}
      <div class="row">
        <div class="col"><label>Quick top-up</label>
          <div class="row">
            <button class="btn" onclick="checkout(5)">Buy 5 credits (£50)</button>
            <button class="btn secondary" onclick="checkout(10)">Buy 10 credits (£100)</button>
          </div>
        </div>
      </div>
      <p class="muted">Payments are via Stripe Checkout.</p>
    </div>
    <div class="card">
      <h3>Developer helpers</h3>
      <p class="muted">Requires ADMIN_CODE set on the server.</p>
      <div class="row">
        <button class="btn" onclick="addTest(10)">+10 test credits</button>
      </div>
    </div>
    <script>
      async function checkout(credits){
        const r = await fetch('/api/checkout/create', {{
          method:'POST',
          headers:{{'Content-Type':'application/json'}},
          body: JSON.stringify({{credits}})
        }});
        const j = await r.json();
        if(!j.ok) return alert(j.error || 'Checkout failed');
        location.href = j.url;
      }
      async function addTest(n){{
        const code = prompt("Admin code?");
        if(!code) return;
        const r = await fetch('/debug/add_credits?n='+n+'&code='+encodeURIComponent(code));
        const j = await r.json();
        alert(j.ok ? ('Credits: '+j.credits) : (j.detail || 'Denied'));
        location.reload();
      }}
    </script>
    """
    return shell(body, user)

def tool_html(user: sqlite3.Row) -> str:
    body = f"""
    <div class="card">
      <h1>Image Timestamp Tool</h1>
      <p class="muted">Credits available: <strong>{user['credits']}</strong> (1 credit per run)</p>
      <form id="frm" class="row" action="/api/process?download=1" method="post" enctype="multipart/form-data">
        <div class="col">
          <label>Date to stamp</label>
          <input required name="date_to_use" placeholder="e.g. 30 May 2025" />
        </div>
        <div class="col">
          <label>Mode</label>
          <select name="mode" id="mode">
            <option value="single">Single image</option>
            <option value="multiple">Multiple images (random times)</option>
          </select>
        </div>
        <div class="col">
          <label>Crop from bottom (px)</label>
          <input required type="number" min="0" value="60" name="crop_bottom_px" />
        </div>
        <div class="col">
          <label>Start time</label>
          <input required type="time" step="1" value="13:00:00" name="start_time" id="start_time">
        </div>
        <div class="col">
          <label>End time <span class="muted">(multiple)</span></label>
          <input type="time" step="1" value="15:00:00" name="end_time" id="end_time">
        </div>
        <div class="col" style="flex-basis:100%">
          <label>Image(s)</label>
          <input required type="file" name="images" id="images" accept="image/*" multiple />
          <p class="muted">Single = uses the Start time. Multiple = random times between Start and End; you’ll get a ZIP.</p>
        </div>
        <div class="col" style="flex-basis:100%">
          <button class="btn" type="submit">Process</button>
          <a class="link" href="/billing">Billing</a>
        </div>
      </form>
    </div>
    <script>
      const modeSel = document.getElementById('mode');
      const endTime = document.getElementById('end_time');
      function toggleEnd(){ const m = modeSel.value; endTime.disabled = (m !== 'multiple'); endTime.required = (m === 'multiple'); }
      modeSel.addEventListener('change', toggleEnd); toggleEnd();
    </script>
    """
    return shell(body, user)

# ---------- Pages ----------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user = get_user_by_id(request.session.get("user_id")) if request.session.get("user_id") else None
    return HTMLResponse(home_html(user))

@app.get("/register", response_class=HTMLResponse)
def register_page():
    return HTMLResponse(auth_form("Register", "/register"))

@app.post("/register")
async def register_post(request: Request):
    form = await request.form()
    email = (form.get("email") or "").strip().lower()
    password = form.get("password") or ""
    try:
        validate_email(email)
    except EmailNotValidError as e:
        return HTMLResponse(auth_form("Register", "/register", error=str(e)))
    if len(password) < 6:
        return HTMLResponse(auth_form("Register", "/register", error="Password must be at least 6 characters."))
    if get_user_by_email(email):
        return HTMLResponse(auth_form("Register", "/register", error="Email already registered. Please log in."))
    uid = create_user(email, password)
    request.session["user_id"] = uid
    return RedirectResponse(url="/tool", status_code=HTTP_302_FOUND)

@app.get("/login", response_class=HTMLResponse)
def login_page():
    return HTMLResponse(auth_form("Log in", "/login"))

@app.post("/login")
async def login_post(request: Request):
    form = await request.form()
    email = (form.get("email") or "").strip().lower()
    password = form.get("password") or ""
    user = get_user_by_email(email)
    if not user or not check_password(password, user["password_hash"]):
        return HTMLResponse(auth_form("Log in", "/login", error="Invalid email or password."))
    request.session["user_id"] = user["id"]
    return RedirectResponse(url="/tool", status_code=HTTP_302_FOUND)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=HTTP_302_FOUND)

@app.get("/billing", response_class=HTMLResponse)
def billing_page(request: Request):
    user = require_user(request)
    return HTMLResponse(billing_html(user))

@app.get("/tool", response_class=HTMLResponse)
def tool_page(request: Request):
    user = require_user(request)
    return HTMLResponse(tool_html(user))

# ---------- Debug top-up (guarded by ADMIN_CODE) ----------
@app.get("/debug/add_credits")
def debug_add_credits(request: Request, n: int = 10, code: Optional[str] = None):
    if not ADMIN_CODE or code != ADMIN_CODE:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = require_user(request)
    new_bal = add_credits(user["id"], n)
    return {"ok": True, "credits": new_bal}

# ---------- Stripe Checkout ----------
@app.post("/api/checkout/create")
async def create_checkout_session(request: Request):
    user = require_user(request)
    if not STRIPE_SECRET_KEY or not STRIPE_PRICE_ID:
        return JSONResponse({"ok": False, "error": "Stripe not configured."})
    data = await request.json()
    credits = int(data.get("credits") or 0)
    if credits < 1:
        return JSONResponse({"ok": False, "error": "Invalid credits quantity."})

    # min purchase of 5 credits if you want strict: uncomment next 2 lines
    # if credits < 5:
    #     return JSONResponse({"ok": False, "error": "Minimum purchase is 5 credits."})

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": credits}],
            success_url=f"{APP_BASE_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{APP_BASE_URL}/billing",
            metadata={"user_id": str(user["id"]), "credits": str(credits)}
        )
        return {"ok": True, "url": session.url}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})

@app.get("/billing/success", response_class=HTMLResponse)
def billing_success(request: Request, session_id: str):
    user = require_user(request)
    if not STRIPE_SECRET_KEY:
        return HTMLResponse(billing_html(user, flash="Stripe not configured."))

    # Verify with Stripe before crediting
    try:
        sess = stripe.checkout.Session.retrieve(session_id, expand=["line_items"])
        if sess.payment_status != "paid":
            return HTMLResponse(billing_html(user, flash="Payment not completed."))
        # Prevent double-credit: record if unseen
        conn = db(); cur = conn.cursor()
        cur.execute("SELECT id FROM payments WHERE session_id = ?", (session_id,))
        seen = cur.fetchone()
        if not seen:
            # Determine credits from line items (sum quantities)
            qty = 0
            for item in (sess.line_items["data"] or []):
                qty += int(item.get("quantity") or 0)
            credited = add_credits(user["id"], qty)
            cur.execute(
                "INSERT INTO payments (user_id, session_id, credits, amount, currency, status, created_at) VALUES (?,?,?,?,?,?,?)",
                (user["id"], session_id, qty, int(sess.amount_total or 0), (sess.currency or "gbp").upper(), sess.payment_status, datetime.utcnow().isoformat())
            )
            conn.commit()
        conn.close()
        # reload user
        fresh = get_user_by_id(user["id"])
        return HTMLResponse(billing_html(fresh, flash="Payment confirmed. Credits added."))
    except Exception as e:
        return HTMLResponse(billing_html(user, flash=f"Could not verify payment: {e}"))

# ---------- Core processing ----------
async def _process_core(user_id: int,
    date_to_use: str,
    mode: str,
    crop_bottom_px: int,
    start_time: str,
    end_time: Optional[str],
    files: List[UploadFile]
):
    if not files:
        raise HTTPException(status_code=400, detail="Please upload at least one image.")

    try:
        start_dt = _parse_time_str(start_time)
        end_dt = _parse_time_str(end_time) if end_time else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM or HH:MM:SS.")

    # SINGLE
    if mode == "single":
        spend_credit(user_id)
        f = files[0]
        binary = await f.read()
        stamp_text = f"{date_to_use}, {start_dt.strftime('%H:%M:%S')}"
        stamped = _stamp_image(binary, stamp_text, crop_bottom_px)
        headers = {"Content-Disposition": f'attachment; filename="{os.path.splitext(f.filename or "image")[0]}_stamped.jpg"'}
        return StreamingResponse(io.BytesIO(stamped), media_type="image/jpeg", headers=headers)

    # MULTIPLE
    if mode == "multiple":
        if end_dt is None:
            raise HTTPException(status_code=400, detail="End time is required for multiple mode.")
        if end_dt <= start_dt:
            raise HTTPException(status_code=400, detail="End time must be after start time.")
        n = len(files)
        total_secs = int((end_dt - start_dt).total_seconds())
        if total_secs <= 0:
            raise HTTPException(status_code=400, detail="Invalid time range.")

        # Spend a single credit for the run (not per image)
        spend_credit(user_id)

        if total_secs >= n:
            random_offsets = sorted(random.sample(range(total_secs), k=n))
        else:
            random_offsets = sorted([int(i * total_secs / max(1, n - 1)) for i in range(n)])

        mem_zip = io.BytesIO()
        with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for idx, f in enumerate(files):
                binary = await f.read()
                ts = start_dt + timedelta(seconds=int(random_offsets[idx]))
                text = f"{date_to_use}, {ts.strftime('%H:%M:%S')}"
                stamped = _stamp_image(binary, text, crop_bottom_px)
                base = os.path.splitext(f.filename or f"image_{idx+1}.jpg")[0]
                zf.writestr(f"{base}_stamped.jpg", stamped)
        mem_zip.seek(0)
        headers = {"Content-Disposition": 'attachment; filename="stamped_images.zip"'}
        return StreamingResponse(mem_zip, media_type="application/zip", headers=headers)

    raise HTTPException(status_code=400, detail="Mode must be 'single' or 'multiple'.")

@app.post("/api/process")
async def process_images(
    request: Request,
    date_to_use: str = Form(...),
    mode: str = Form(...),
    crop_bottom_px: int = Form(...),
    start_time: str = Form(...),
    end_time: Optional[str] = Form(None),
    images: List[UploadFile] = File(...)
):
    user = require_user(request)
    return await _process_core(user["id"], date_to_use, mode, crop_bottom_px, start_time, end_time, images)

# Back-compat
@app.post("/api/stamp")
async def legacy_stamp(
    request: Request,
    date_to_use: str = Form(...),
    mode: str = Form(...),
    crop_bottom_px: int = Form(...),
    start_time: str = Form(...),
    end_time: Optional[str] = Form(None),
    images: List[UploadFile] = File(...)
):
    user = require_user(request)
    return await _process_core(user["id"], date_to_use, mode, crop_bottom_px, start_time, end_time, images)
