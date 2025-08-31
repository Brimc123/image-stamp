# auth.py — drop-in (Step 1)
from __future__ import annotations
import os, sqlite3, secrets, hashlib, hmac, time, json
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

# -----------------------------
# Config (business rules)
# -----------------------------
DB_FILE = os.environ.get("DB_FILE", "/var/data/app.db")
SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "imgstamp_session")
SESSION_TTL_SECONDS = 60 * 60 * 24 * 14  # 14 days

# Pricing / policy
CREDIT_COST_GBP = 10          # £10 per credit
MIN_TOPUP_CREDITS = 5         # min top-up size = 5 credits (£50)

# Admin bootstrap (optional)
ADMIN_EMAIL = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
ADMIN_SECRET = os.environ.get("ADMIN_SECRET")  # used by admin endpoints (next step)

router = APIRouter()

# -----------------------------
# DB helpers
# -----------------------------
def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    con = sqlite3.connect(DB_FILE, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def _ensure_db() -> None:
    con = _conn()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            credits INTEGER NOT NULL DEFAULT 0,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            endpoint TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            meta TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    con.commit()

    # Bootstrap admin flag if ADMIN_EMAIL is provided
    if ADMIN_EMAIL:
        cur = con.execute("SELECT id FROM users WHERE email=?", (ADMIN_EMAIL,))
        row = cur.fetchone()
        if row:
            con.execute("UPDATE users SET is_admin=1 WHERE id=?", (row["id"],))
            con.commit()
    con.close()

_ensure_db()

# -----------------------------
# Password hashing (PBKDF2)
# -----------------------------
def _hash_password(password: str, *, rounds: int = 200_000) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"pbkdf2${rounds}${salt.hex()}${dk.hex()}"

def _verify_password(password: str, stored: str) -> bool:
    try:
        scheme, rounds_s, salt_hex, hash_hex = stored.split("$", 3)
        if scheme != "pbkdf2":
            return False
        rounds = int(rounds_s)
        salt = bytes.fromhex(salt_hex)
        want = bytes.fromhex(hash_hex)
        got = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
        return hmac.compare_digest(got, want)
    except Exception:
        return False

# -----------------------------
# Schemas
# -----------------------------
class SignupIn(BaseModel):
    email: str
    password: str

class LoginIn(BaseModel):
    email: str
    password: str

def _norm_email(s: str) -> str:
    s = (s or "").strip().lower()
    if "@" not in s or "." not in s.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Invalid email")
    return s

# -----------------------------
# Session/cookie helpers
# -----------------------------
def _set_cookie(resp: Response, token: str) -> None:
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,      # keep True on https
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )

def _clear_cookie(resp: Response) -> None:
    resp.delete_cookie(SESSION_COOKIE_NAME, path="/")

def _create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    con = _conn()
    con.execute(
        "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
        (token, user_id, int(time.time())),
    )
    con.commit()
    con.close()
    return token

def _get_session(token: str) -> Optional[sqlite3.Row]:
    con = _conn()
    cur = con.execute("SELECT * FROM sessions WHERE token=?", (token,))
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    if int(time.time()) - row["created_at"] > SESSION_TTL_SECONDS:
        con = _conn()
        con.execute("DELETE FROM sessions WHERE token=?", (token,))
        con.commit()
        con.close()
        return None
    return row

def _get_user_by_email(email: str) -> Optional[sqlite3.Row]:
    con = _conn()
    cur = con.execute("SELECT * FROM users WHERE email=?", (email.lower(),))
    row = cur.fetchone()
    con.close()
    return row

def _get_user(user_id: int) -> Optional[sqlite3.Row]:
    con = _conn()
    cur = con.execute("SELECT * FROM users WHERE id=?", (user_id,))
    row = cur.fetchone()
    con.close()
    return row

# -----------------------------
# Public dependency
# -----------------------------
def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    sess = _get_session(token)
    if not sess:
        return None
    user = _get_user(sess["user_id"])
    if not user:
        return None
    return {
        "id": user["id"],
        "email": user["email"],
        "credits": user["credits"],
        "is_admin": bool(user["is_admin"]),
    }

# -----------------------------
# Credit helpers (used by app)
# -----------------------------
def db_decrement_credit(user_id: int, *, amount: int = 1) -> None:
    con = _conn()
    cur = con.execute("SELECT credits FROM users WHERE id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        con.close()
        raise HTTPException(status_code=404, detail="User not found")
    if row["credits"] < amount:
        con.close()
        raise HTTPException(status_code=402, detail="Insufficient credits")
    con.execute("UPDATE users SET credits = credits - ? WHERE id=?", (amount, user_id))
    con.commit()
    con.close()

def db_increment_credit(user_id: int, *, amount: int) -> None:
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Top-up amount must be positive")
    con = _conn()
    con.execute("UPDATE users SET credits = credits + ? WHERE id=?", (amount, user_id))
    con.commit()
    con.close()

def db_log_usage(user_id: int, endpoint: str, meta: Dict[str, Any] | str = "") -> None:
    if isinstance(meta, dict):
        meta = json.dumps(meta)
    con = _conn()
    con.execute(
        "INSERT INTO usage_log (user_id, endpoint, meta) VALUES (?, ?, ?)",
        (user_id, endpoint, meta),
    )
    con.commit()
    con.close()

# -----------------------------
# Routes
# -----------------------------
@router.get("/config")
def config():
    return {
        "credit_cost_gbp": CREDIT_COST_GBP,
        "min_topup_credits": MIN_TOPUP_CREDITS,
        "admin_enabled": bool(ADMIN_SECRET),
    }

@router.post("/signup")
def signup(payload: SignupIn):
    email = _norm_email(payload.email)
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password too short")
    existing = _get_user_by_email(email)
    con = _conn()
    if existing:
        con.execute(
            "UPDATE users SET password_hash=? WHERE email=?",
            (_hash_password(payload.password), email),
        )
    else:
        # New accounts start with 0 credits (top-up required)
        con.execute(
            "INSERT INTO users (email, password_hash, credits) VALUES (?, ?, ?)",
            (email, _hash_password(payload.password), 0),
        )
        # auto-admin if matches ADMIN_EMAIL
        if ADMIN_EMAIL and email == ADMIN_EMAIL:
            con.execute("UPDATE users SET is_admin=1 WHERE email=?", (email,))
    con.commit()
    con.close()
    return {"ok": True, "message": "Account ready"}

@router.post("/login")
def login(payload: LoginIn, response: Response):
    email = _norm_email(payload.email)
    row = _get_user_by_email(email)
    if not row or not _verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = _create_session(row["id"])
    _set_cookie(response, token)
    return {"ok": True, "email": row["email"], "credits": row["credits"], "is_admin": bool(row["is_admin"])}

@router.post("/logout")
def logout(response: Response, request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        con = _conn()
        con.execute("DELETE FROM sessions WHERE token=?", (token,))
        con.commit()
        con.close()
    _clear_cookie(response)
    return {"ok": True}

@router.get("/me")
def me(user = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    return {
        "email": user["email"],
        "credits": user["credits"],
        "is_admin": user["is_admin"],
        "credit_cost_gbp": CREDIT_COST_GBP,
        "min_topup_credits": MIN_TOPUP_CREDITS,
    }
