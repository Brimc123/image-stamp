# server.py — minimal, crash-safe routes for /, /app, /billing, /topup, /admin
# Uses DB_PATH or DB_FILE; falls back to ./app.db if /var/data isn't available.

import os, hmac, base64, hashlib, sqlite3
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

# ---------- ENV ----------
ADMIN_EMAIL = (os.environ.get("ADMIN_EMAIL") or "").lower().strip()
APP_SECRET = os.environ.get("APP_SECRET") or os.environ.get("ADMIN_SECRET") or "change_me"
ALLOWED_ORIGINS = [x.strip() for x in (os.environ.get("ALLOWED_ORIGINS") or "").split(",") if x.strip()]

# price rules
CREDIT_PRICE_PENNIES = 1000   # £10/credit
BUNDLE_MIN_CREDITS    = 5     # min top-up = 5 credits
BUNDLE_MIN_PRICE_PENNIES = CREDIT_PRICE_PENNIES * BUNDLE_MIN_CREDITS

def _resolve_db_path() -> str:
    # prefer DB_PATH, then DB_FILE, else ./app.db
    cand = os.environ.get("DB_PATH") or os.environ.get("DB_FILE") or "app.db"
    d = os.path.dirname(cand)
    if d and not os.path.exists(d):
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            # fall back to local file if directory cannot be created
            return "app.db"
    return cand

DB_PATH = _resolve_db_path()

# ---------- APP ----------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins = ALLOWED_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=APP_SECRET,
    same_site="lax",
    https_only=True,
    session_cookie=os.environ.get("SESSION_COOKIE_NAME") or "imgstamp_session",
)

# ---------- DB ----------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as conn:
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            credits INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS usage(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            credits_change INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS topups(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            bundle_credits INTEGER NOT NULL,
            bundle_price_pennies INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )""")
init_db()

# ---------- UTILS ----------
def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 120000)
    return base64.b64encode(salt + dk).decode()

def check_password(pw: str, blob: str) -> bool:
    raw = base64.b64decode(blob.encode())
    salt, dk = raw[:16], raw[16:]
    ndk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 120000)
    return hmac.compare_digest(dk, ndk)

def me(request: Request) -> Optional[sqlite3.Row]:
    email = request.session.get("email")
    if not email: return None
    with db() as conn:
        r = conn.execute("SELECT * FROM users WHERE email=?", (email.lower(),)).fetchone()
    return r

def require_login(request: Request) -> sqlite3.Row:
    u = me(request)
    if not u:
        raise HTTPException(status_code=302, detail="login required")
    return u

def is_admin(u: sqlite3.Row) -> bool:
    return ADMIN_EMAIL and u["email"].lower() == ADMIN_EMAIL

# ---------- DEBUG HELP ----------
@app.get("/__whoami", response_class=PlainTextResponse)
def whoami():
    return f"server.py active · DB_PATH={DB_PATH}"

# ---------- BASIC PAGES ----------
@app.get("/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat(), "db": DB_PATH}

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    u = me(request)
    if u:
        links = '<a href="/app">App</a> · <a href="/billing">Billing</a> · <a href="/admin">Admin</a> · <a href="/logout">Logout</a>'
        return HTMLResponse(f"<html><body style='font-family:system-ui;margin:2rem'><h2>IMAGE STAMP</h2>"
                            f"<p>Logged in as <b>{u['email']}</b> — Credits: <b>{u['credits']}</b></p><p>{links}</p></body></html>")
    return HTMLResponse("<html><body style='font-family:system-ui;margin:2rem'><h2>IMAGE STAMP</h2>"
                        "<p><a href='/signup'>Create account</a> or <a href='/login'>Log in</a></p></body></html>")

# ---------- AUTH ----------
@app.get("/signup", response_class=HTMLResponse)
def signup_form():
    return HTMLResponse("""
    <html><body style="font-family:system-ui;margin:2rem;max-width:420px">
      <h3>Create account</h3>
      <form method="post" action="/signup">
        <label>Email</label><br><input name="email" type="email" required style="width:100%"><br><br>
        <label>Password</label><br><input name="password" type="password" required style="width:100%"><br><br>
        <button type="submit">Sign up</button>
      </form>
      <p>Have an account? <a href="/login">Log in</a></p>
    </body></html>""")

@app.post("/signup")
def signup(email: str = Form(...), password: str = Form(...)):
    email = email.lower().strip()
    with db() as conn:
        try:
            conn.execute("INSERT INTO users(email,password_hash,credits,created_at) VALUES(?,?,?,?)",
                         (email, hash_password(password), 0, datetime.utcnow().isoformat()))
        except sqlite3.IntegrityError:
            return PlainTextResponse("email already exists", status_code=400)
    return RedirectResponse(url="/login", status_code=302)

@app.get("/login", response_class=HTMLResponse)
def login_form():
    return HTMLResponse("""
    <html><body style="font-family:system-ui;margin:2rem;max-width:420px">
      <h3>Log in</h3>
      <form method="post" action="/login">
        <label>Email</label><br><input name="email" type="email" required style="width:100%"><br><br>
        <label>Password</label><br><input name="password" type="password" required style="width:100%"><br><br>
        <button type="submit">Log in</button>
      </form>
      <p>No account? <a href="/signup">Sign up</a></p>
    </body></html>""")

@app.post("/login")
def do_login(request: Request, email: str = Form(...), password: str = Form(...)):
    email = email.lower().strip()
    with db() as conn:
        u = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not u or not check_password(password, u["password_hash"]):
        return PlainTextResponse("invalid credentials", status_code=400)
    request.session["email"] = email
    return RedirectResponse(url="/", status_code=302)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)

# ---------- APP ----------
@app.get("/app", response_class=HTMLResponse)
def app_page(request: Request):
    u = require_login(request)
    return HTMLResponse(f"""
    <html><body style="font-family:system-ui;margin:2rem">
      <h3>Stamp & Download</h3>
      <p>Credits remaining: <b>{u['credits']}</b></p>
      <form method="post" action="/use-credit">
        <button type="submit">Simulate a stamp (uses 1 credit)</button>
      </form>
      <p><a href="/billing">Go to Billing</a></p>
    </body></html>""")

@app.post("/use-credit")
def use_credit(request: Request):
    u = require_login(request)
    with db() as conn:
        row = conn.execute("SELECT credits FROM users WHERE id=?", (u["id"],)).fetchone()
        if not row or row["credits"] < 1:
            return PlainTextResponse("Not enough credits. Please top up.", status_code=402)
        conn.execute("UPDATE users SET credits=credits-1 WHERE id=?", (u["id"],))
        conn.execute("INSERT INTO usage(user_id,action,credits_change,created_at) VALUES(?,?,?,?)",
                     (u["id"], "stamp", -1, datetime.utcnow().isoformat()))
    return RedirectResponse(url="/app", status_code=302)

# ---------- BILLING ----------
@app.get("/billing", response_class=HTMLResponse)
def billing(request: Request):
    u = require_login(request)
    with db() as conn:
        me_row = conn.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone()
        topups = conn.execute("SELECT * FROM topups WHERE user_id=? ORDER BY id DESC LIMIT 25",(u["id"],)).fetchall()
        uses   = conn.execute("SELECT * FROM usage WHERE user_id=? ORDER BY id DESC LIMIT 25",(u["id"],)).fetchall()
    credits = me_row["credits"] if me_row else 0
    topup_rows = "".join([f"<tr><td>{t['created_at']}</td><td>+{t['bundle_credits']}</td><td>£{t['bundle_price_pennies']/100:.2f}</td></tr>" for t in topups]) or "<tr><td colspan=3>No top-ups yet</td></tr>"
    usage_rows = "".join([f"<tr><td>{x['created_at']}</td><td>{x['action']}</td><td>{x['credits_change']}</td></tr>" for x in uses]) or "<tr><td colspan=3>No usage yet</td></tr>"
    return HTMLResponse(f"""
    <html><body style="font-family:system-ui;margin:2rem">
      <h3>Billing</h3>
      <p>Credits: <b>{credits}</b> · Price: £10/credit · Minimum top-up: 5 credits (£50)</p>
      <form method="post" action="/topup"><button type="submit">Top up 5 credits (£50)</button></form>
      <h4 style="margin-top:2rem">Recent Top-ups</h4>
      <table border="1" cellpadding="6" cellspacing="0"><tr><th>When</th><th>Credits</th><th>Charged</th></tr>{topup_rows}</table>
      <h4 style="margin-top:2rem">Recent Usage</h4>
      <table border="1" cellpadding="6" cellspacing="0"><tr><th>When</th><th>Action</th><th>Credits Δ</th></tr>{usage_rows}</table>
      <p style="margin-top:1rem"><a href="/">Back</a></p>
    </body></html>""")

@app.post("/topup")
def topup(request: Request):
    u = require_login(request)
    with db() as conn:
        conn.execute("UPDATE users SET credits=credits+? WHERE id=?", (BUNDLE_MIN_CREDITS, u["id"]))
        now = datetime.utcnow().isoformat()
        conn.execute("INSERT INTO topups(user_id,bundle_credits,bundle_price_pennies,created_at) VALUES(?,?,?,?)",
                     (u["id"], BUNDLE_MIN_CREDITS, BUNDLE_MIN_PRICE_PENNIES, now))
        conn.execute("INSERT INTO usage(user_id,action,credits_change,created_at) VALUES(?,?,?,?)",
                     (u["id"], "topup", +BUNDLE_MIN_CREDITS, now))
    return RedirectResponse(url="/billing", status_code=302)

# ---------- ADMIN ----------
@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    u = require_login(request)
    if not is_admin(u):
        return HTMLResponse("<html><body style='font-family:system-ui;margin:2rem'><h3>Admin</h3><p>Access denied.</p></body></html>", status_code=403)
    with db() as conn:
        users = conn.execute("SELECT id,email,credits,created_at FROM users ORDER BY id DESC").fetchall()
        recent = conn.execute("""
            SELECT u.email, g.action, g.credits_change, g.created_at
            FROM usage g JOIN users u ON u.id=g.user_id ORDER BY g.id DESC LIMIT 100
        """).fetchall()
        tops = conn.execute("""
            SELECT u.email, t.bundle_credits, t.bundle_price_pennies, t.created_at
            FROM topups t JOIN users u ON u.id=t.user_id ORDER BY t.id DESC LIMIT 100
        """).fetchall()
    ur = "".join([f"<tr><td>{r['email']}</td><td>{r['credits']}</td><td>{r['created_at']}</td></tr>" for r in users]) or "<tr><td colspan=3>No users</td></tr>"
    gr = "".join([f"<tr><td>{r['created_at']}</td><td>{r['email']}</td><td>{r['action']}</td><td>{r['credits_change']}</td></tr>" for r in recent]) or "<tr><td colspan=4>No usage</td></tr>"
    tr = "".join([f"<tr><td>{r['created_at']}</td><td>{r['email']}</td><td>+{r['bundle_credits']}</td><td>£{r['bundle_price_pennies']/100:.2f}</td></tr>" for r in tops]) or "<tr><td colspan=4>No top-ups</td></tr>"
    return HTMLResponse(f"""
    <html><body style="font-family:system-ui;margin:2rem">
      <h3>Admin Dashboard</h3>
      <p>DB: {DB_PATH}</p>
      <h4>Users</h4><table border="1" cellpadding="6" cellspacing="0"><tr><th>Email</th><th>Credits</th><th>Created</th></tr>{ur}</table>
      <h4 style="margin-top:2rem">Recent Usage</h4><table border="1" cellpadding="6" cellspacing="0"><tr><th>When</th><th>User</th><th>Action</th><th>Credits Δ</th></tr>{gr}</table>
      <h4 style="margin-top:2rem">Recent Top-ups</h4><table border="1" cellpadding="6" cellspacing="0"><tr><th>When</th><th>User</th><th>Credits</th><th>Charged</th></tr>{tr}</table>
      <p style="margin-top:1rem"><a href="/">Back</a></p>
    </body></html>""")

# ---------- GENERIC ERROR: show message instead of blank 500 ----------
@app.exception_handler(Exception)
async def all_errors(request: Request, exc: Exception):
    return HTMLResponse(f"<pre style='white-space:pre-wrap;font-family:ui-monospace;padding:1rem'>"
                        f"Error: {type(exc).__name__}\n{str(exc)}\n</pre>", status_code=500)
