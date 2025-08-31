# auth.py — cookie fix for custom domain + auto-migration
from __future__ import annotations
import os, sqlite3, secrets, hashlib, hmac, time, json
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

DB_FILE = os.environ.get("DB_FILE", "/var/data/app.db")
SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "imgstamp_session")
SESSION_TTL_SECONDS = 60 * 60 * 24 * 14  # 14 days

# Business rules
CREDIT_COST_GBP = 10
MIN_TOPUP_CREDITS = 5

# Admin bootstrap
ADMIN_EMAIL = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
ADMIN_SECRET = os.environ.get("ADMIN_SECRET")

router = APIRouter()

# -----------------------------
# DB helpers
# -----------------------------
def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    con = sqlite3.connect(DB_FILE, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def _table_cols(con: sqlite3.Connection, name: str) -> set[str]:
    try:
        cur = con.execute(f"PRAGMA table_info({name})")
        return {r["name"] for r in cur.fetchall()}
    except Exception:
        return set()

def _ensure_db() -> None:
    con = _conn()
    cur = con.cursor()
    # Create latest schema
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

    # ---- MIGRATION: if old 'users' table existed without 'id'
    try:
        cols = _table_cols(con, "users")
        if "id" not in cols:
            cur.execute("ALTER TABLE users RENAME TO users_old")
            con.commit()
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
            con.commit()
            old_cols = _table_cols(con, "users_old")
            pass_col = "password_hash" if "password_hash" in old_cols else ("password" if "password" in old_cols else None)
            if pass_col:
                credits_expr = "COALESCE(credits,0)" if "credits" in old_cols else "0"
                admin_expr   = "COALESCE(is_admin,0)" if "is_admin" in old_cols else "0"
                created_expr = "COALESCE(created_at, datetime('now'))" if "created_at" in old_cols else "datetime('now')"
                cur.execute(f"""
                    INSERT INTO users (email, password_hash, credits, is_admin, created_at)
                    SELECT email, {pass_col}, {credits_expr}, {admin_expr}, {created_expr}
                    FROM users_old
                """)
            cur.execute("DROP TABLE IF EXISTS users_old")
            con.commit()
    except Exception:
        pass

    # Bootstrap admin flag if ADMIN_EMAIL matches an existing user
    if ADMIN_EMAIL:
        cur = con.execute("SELECT rowid FROM users WHERE email=?", (ADMIN_EMAIL,))
        if cur.fetchone():
            con.execute("UPDATE users SET is_admin=1 WHERE email=?", (ADMIN_EMAIL,))
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
# Cookie helpers (custom domain safe)
# -----------------------------
from typing import Optional
def _cookie_domain(request: Request) -> Optional[str]:
    host = (request.headers.get("host") or request.url.hostname or "").split(":")[0]
    if not host:  # local dev etc.
        return None
    if host.endswith(".onrender.com") or host in ("localhost", "127.0.0.1"):
        return None
    return host  # e.g. autodate.co.uk

def _set_cookie(request: Request, resp: Response, token: str) -> None:
    domain = _cookie_domain(request)
    secure = (request.url.scheme == "https")
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
        path="/",
        domain=domain,
    )

def _clear_cookie(request: Request, resp: Response) -> None:
    domain = _cookie_domain(request)
    resp.delete_cookie(SESSION_COOKIE_NAME, path="/", domain=domain)

# -----------------------------
# DB lookups
# -----------------------------
def _get_user_by_email(email: str) -> Optional[sqlite3.Row]:
    con = _conn()
    cur = con.execute("SELECT * FROM users WHERE email=?", (email.lower(),))
    row = cur.fetchone(); con.close()
    return row

def _get_user(user_id: int) -> Optional[sqlite3.Row]:
    con = _conn()
    cur = con.execute("SELECT * FROM users WHERE id=?", (user_id,))
    row = cur.fetchone(); con.close()
    return row

def _create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    con = _conn()
    con.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
                (token, user_id, int(time.time())))
    con.commit(); con.close()
    return token

def _get_session(token: str) -> Optional[sqlite3.Row]:
    con = _conn()
    cur = con.execute("SELECT * FROM sessions WHERE token=?", (token,))
    row = cur.fetchone(); con.close()
    if not row:
        return None
    if int(time.time()) - row["created_at"] > SESSION_TTL_SECONDS:
        con = _conn(); con.execute("DELETE FROM sessions WHERE token=?", (token,)); con.commit(); con.close()
        return None
    return row

# -----------------------------
# Current user
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
# Credit helpers
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
    con.commit(); con.close()

def db_increment_credit(user_id: int, *, amount: int) -> None:
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Top-up amount must be positive")
    con = _conn()
    con.execute("UPDATE users SET credits = credits + ? WHERE id=?", (amount, user_id))
    con.commit(); con.close()

def db_log_usage(user_id: int, endpoint: str, meta: Dict[str, Any] | str = "") -> None:
    if isinstance(meta, dict):
        meta = json.dumps(meta)
    con = _conn()
    con.execute("INSERT INTO usage_log (user_id, endpoint, meta) VALUES (?, ?, ?)",
                (user_id, endpoint, meta))
    con.commit(); con.close()

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
        con.execute("UPDATE users SET password_hash=? WHERE email=?",
                    (_hash_password(payload.password), email))
    else:
        con.execute("INSERT INTO users (email, password_hash, credits) VALUES (?, ?, ?)",
                    (email, _hash_password(payload.password), 0))
        if ADMIN_EMAIL and email == ADMIN_EMAIL:
            con.execute("UPDATE users SET is_admin=1 WHERE email=?", (email,))
    con.commit(); con.close()
    return {"ok": True, "message": "Account ready"}

@router.post("/login")
def login(payload: LoginIn, response: Response, request: Request):
    email = _norm_email(payload.email)
    row = _get_user_by_email(email)
    if not row or not _verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = _create_session(row["id"])
    _set_cookie(request, response, token)
    return {"ok": True, "email": row["email"], "credits": row["credits"], "is_admin": bool(row["is_admin"])}

@router.post("/logout")
def logout(response: Response, request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        con = _conn()
        con.execute("DELETE FROM sessions WHERE token=?", (token,))
        con.commit(); con.close()
    _clear_cookie(request, response)
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
