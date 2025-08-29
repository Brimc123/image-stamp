# auth.py
import os, hmac, bcrypt, secrets, time
import sqlite3
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, Response

router = APIRouter(prefix="/auth")

# --- ENV VARS ---
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")
ALLOW_DEMO_TOPUP = os.getenv("ALLOW_DEMO_TOPUP", "0") == "1"
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "imgstamp_session")
SESSION_COOKIE_DOMAIN = os.getenv("SESSION_COOKIE_DOMAIN", None)

DB_FILE = "app.db"

# --- Helpers ---

def ct_equals(a: str, b: str) -> bool:
    """Constant-time string comparison"""
    return hmac.compare_digest(a.encode(), b.encode())

def db():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_pw(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False

def set_session_cookie(resp: Response, value: str, max_age_days: int = 14):
    secure = True  # always assume HTTPS in prod
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=value,
        max_age=max_age_days * 86400,
        httponly=True,
        secure=secure,
        samesite="Strict",
        domain=SESSION_COOKIE_DOMAIN if SESSION_COOKIE_DOMAIN else None,
        path="/"
    )

def clear_session_cookie(resp: Response):
    resp.delete_cookie(SESSION_COOKIE_NAME)

def require_admin(request: Request):
    got = request.headers.get("x-admin-secret", "")
    if not ADMIN_SECRET or not got or not ct_equals(got, ADMIN_SECRET):
        raise HTTPException(status_code=403, detail="Forbidden")

# --- Session management ---

def create_session(user_id: int) -> str:
    token = secrets.token_hex(32)
    expires = int(time.time()) + (14 * 86400)
    with db() as conn:
        conn.execute("INSERT INTO sessions(user_id, token, expires) VALUES(?,?,?)",
                     (user_id, token, expires))
        conn.commit()
    return token

def get_user_by_session(token: str):
    if not token:
        return None
    now = int(time.time())
    with db() as conn:
        row = conn.execute(
            """SELECT u.id,u.email,u.credits,u.is_active 
               FROM users u 
               JOIN sessions s ON u.id=s.user_id 
               WHERE s.token=? AND s.expires>?""",
            (token, now)
        ).fetchone()
    return row

# --- Routes ---

@router.post("/ensure_master")
async def ensure_master(req: Request):
    data = await req.json()
    email = data.get("email","").strip().lower()
    pw = data.get("password","")
    if not email or not pw:
        raise HTTPException(400,"Email and password required")

    with db() as conn:
        if conn.execute("SELECT id FROM users WHERE email=?",(email,)).fetchone():
            raise HTTPException(400,"Email already exists")
        conn.execute("INSERT INTO users(email,password,credits,is_active) VALUES(?,?,?,1)",
                     (email, hash_pw(pw), 0))
        conn.commit()
    return {"ok":True,"msg":"User created"}

@router.post("/login")
async def login(req: Request):
    data = await req.json()
    email = data.get("email","").strip().lower()
    pw = data.get("password","")

    with db() as conn:
        row = conn.execute("SELECT id,password,is_active FROM users WHERE email=?",(email,)).fetchone()
    if not row:
        raise HTTPException(400,"Invalid credentials")

    uid, hashed, active = row
    if not active:
        raise HTTPException(403,"Account locked")
    if not check_pw(pw, hashed):
        raise HTTPException(400,"Invalid credentials")

    token = create_session(uid)
    resp = JSONResponse({"ok":True})
    set_session_cookie(resp, token)
    return resp

@router.post("/logout")
async def logout(req: Request):
    token = req.cookies.get(SESSION_COOKIE_NAME)
    if token:
        with db() as conn:
            conn.execute("DELETE FROM sessions WHERE token=?",(token,))
            conn.commit()
    resp = JSONResponse({"ok":True})
    clear_session_cookie(resp)
    return resp

@router.get("/status")
async def status(req: Request):
    token = req.cookies.get(SESSION_COOKIE_NAME)
    user = get_user_by_session(token)
    if not user:
        return {"logged_in":False}
    uid,email,credits,is_active = user
    return {
        "logged_in":True,
        "email":email,
        "credits":credits,
        "is_active":is_active,
        "credit_cost_gbp": int(os.getenv("CREDIT_COST_GBP","20"))
    }

# --- Credit handling ---

@router.post("/topup_demo")
async def topup_demo(req: Request):
    if not ALLOW_DEMO_TOPUP:
        raise HTTPException(403,"Demo top-up disabled")
    token = req.cookies.get(SESSION_COOKIE_NAME)
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(401,"Not logged in")
    uid,email,credits,is_active = user
    with db() as conn:
        conn.execute("UPDATE users SET credits=credits+5 WHERE id=?",(uid,))
        conn.commit()
    return {"ok":True,"credits":credits+5}

@router.post("/topup_admin")
async def topup_admin(req: Request):
    require_admin(req)
    data = await req.json()
    email = data.get("email","").strip().lower()
    amount = int(data.get("amount",0))
    if amount<=0: raise HTTPException(400,"Invalid amount")
    with db() as conn:
        conn.execute("UPDATE users SET credits=credits+? WHERE email=?",(amount,email))
        conn.commit()
    return {"ok":True}

@router.post("/lock_admin")
async def lock_admin(req: Request):
    require_admin(req)
    data = await req.json()
    email = data.get("email","").strip().lower()
    active = 1 if data.get("is_active",1) else 0
    with db() as conn:
        conn.execute("UPDATE users SET is_active=? WHERE email=?",(active,email))
        conn.commit()
    return {"ok":True,"is_active":active}
