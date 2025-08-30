# auth.py
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import bcrypt
from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
)
from pydantic import BaseModel, EmailStr

# -----------------------------------------------------------------------------
# Router (must be defined before any @router.* decorators)
# -----------------------------------------------------------------------------
router = APIRouter(prefix="/auth", tags=["auth"])

# -----------------------------------------------------------------------------
# Environment & DB
# -----------------------------------------------------------------------------
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "change_me")
ALLOW_DEMO_TOPUP = os.getenv("ALLOW_DEMO_TOPUP", "0") == "1"
DB_FILE = os.getenv("DB_FILE", "app.db")  # sqlite file tracked for demo
CREDIT_COST_GBP = int(os.getenv("CREDIT_COST_GBP", "20"))  # used for billing UI

def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_FILE, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def _ensure_db() -> None:
    con = _conn()
    try:
        cur = con.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                credits INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                typ TEXT NOT NULL,
                credits_used INTEGER NOT NULL,
                ts TEXT NOT NULL
            )
            """
        )
        con.commit()
    finally:
        con.close()

_ensure_db()

# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def _verify_password(pw: str, pw_hash: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), pw_hash.encode("utf-8"))
    except Exception:
        return False

def db_get_user(email: str) -> Optional[sqlite3.Row]:
    con = _conn()
    try:
        cur = con.cursor()
        cur.execute("SELECT * FROM users WHERE email = ?", (email.lower(),))
        return cur.fetchone()
    finally:
        con.close()

def db_create_user(email: str, password: str) -> None:
    if db_get_user(email):
        raise HTTPException(status_code=400, detail="User already exists")
    con = _conn()
    try:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO users (email, password_hash, credits, created_at) VALUES (?,?,?,?)",
            (email.lower(), _hash_password(password), 0, _now_iso()),
        )
        con.commit()
    finally:
        con.close()

def db_add_credits(email: str, amount: int) -> int:
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    con = _conn()
    try:
        cur = con.cursor()
        cur.execute("UPDATE users SET credits = COALESCE(credits,0) + ? WHERE email = ?", (amount, email.lower()))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
        con.commit()
        cur.execute("SELECT credits FROM users WHERE email = ?", (email.lower(),))
        credits = cur.fetchone()["credits"]
        return int(credits)
    finally:
        con.close()

def db_decrement_credit(email: str, amount: int = 1) -> int:
    """Decrease credits for a user and return new balance. Raises if insufficient."""
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    con = _conn()
    try:
        cur = con.cursor()
        cur.execute("SELECT credits FROM users WHERE email = ?", (email.lower(),))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        balance = int(row["credits"])
        if balance < amount:
            raise HTTPException(status_code=402, detail="Not enough credits")
        new_balance = balance - amount
        cur.execute("UPDATE users SET credits = ? WHERE email = ?", (new_balance, email.lower()))
        con.commit()
        return new_balance
    finally:
        con.close()

def db_log_usage(email: str, typ: str, credits_used: int = 1) -> None:
    con = _conn()
    try:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO usage_log (email, typ, credits_used, ts) VALUES (?,?,?,?)",
            (email.lower(), typ, int(credits_used), _now_iso()),
        )
        con.commit()
    finally:
        con.close()

# -----------------------------------------------------------------------------
# Session helpers
# -----------------------------------------------------------------------------
def get_current_user(request: Request) -> sqlite3.Row:
    email = (request.session or {}).get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Not signed in")
    user = db_get_user(email)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# -----------------------------------------------------------------------------
# Pydantic models for JSON requests (UI also sends form-encoded; we support both)
# -----------------------------------------------------------------------------
class SignupIn(BaseModel):
    email: EmailStr
    password: str

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class TopUpIn(BaseModel):
    email: EmailStr
    amount: int

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@router.post("/ensure_master")
def ensure_master() -> dict:
    """
    No-op placeholder to match earlier imports.
    Ensures DB exists and returns ok.
    """
    _ensure_db()
    return {"ok": True}

@router.post("/signup")
async def signup(
    request: Request,
    email: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    body: Optional[SignupIn] = None,
):
    # Support JSON or form
    if body:
        email = body.email
        password = body.password
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")

    db_create_user(email, password)
    # Auto-login
    request.session["email"] = email.lower()
    user = db_get_user(email)
    return {"ok": True, "email": user["email"], "credits": int(user["credits"])}

@router.post("/login")
async def login(
    request: Request,
    email: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    body: Optional[LoginIn] = None,
):
    if body:
        email = body.email
        password = body.password
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")

    user = db_get_user(email)
    if not user or not _verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    request.session["email"] = user["email"]
    return {"ok": True, "email": user["email"], "credits": int(user["credits"])}

@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}

@router.get("/me")
def me(user: sqlite3.Row = Depends(get_current_user)) -> dict:
    return {"email": user["email"], "credits": int(user["credits"])}

@router.get("/credits")
def credits(user: sqlite3.Row = Depends(get_current_user)) -> dict:
    return {"credits": int(user["credits"])}

@router.post("/topup_demo")
def topup_demo(request: Request, user: sqlite3.Row = Depends(get_current_user)) -> dict:
    if not ALLOW_DEMO_TOPUP:
        raise HTTPException(status_code=403, detail="Demo top-up disabled")
    new_balance = db_add_credits(user["email"], 5)
    db_log_usage(user["email"], "topup_demo", 0)
    return {"ok": True, "credits": new_balance}

@router.post("/topup_admin")
def topup_admin(
    request: Request,
    email: Optional[str] = Form(None),
    amount: Optional[int] = Form(None),
    body: Optional[TopUpIn] = None,
):
    # Admin auth (header)
    admin_hdr = request.headers.get("X-Admin-Secret", "")
    if admin_hdr != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Support JSON or form
    if body:
        email = str(body.email)
        amount = int(body.amount) if body.amount is not None else None
    if not email or amount is None:
        raise HTTPException(status_code=400, detail="email and amount are required")

    new_balance = db_add_credits(email, int(amount))
    db_log_usage(email, "topup_admin", 0)
    return {"ok": True, "email": email.lower(), "credits": new_balance}

# -----------------------------------------------------------------------------
# Billing helpers (used by /billing page)
# -----------------------------------------------------------------------------
@router.get("/report/weekly")
def report_weekly(request: Request):
    """Return a very small summary for admin to pull weekly CSV from the /billing page."""
    admin_hdr = request.headers.get("X-Admin-Secret", "")
    if admin_hdr != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    con = _conn()
    try:
        cur = con.cursor()
        cur.execute(
            """
            SELECT email, typ, credits_used, ts
            FROM usage_log
            WHERE ts >= datetime('now', '-7 day')
            ORDER BY ts DESC
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        con.close()

    return {
        "ok": True,
        "credit_cost_gbp": CREDIT_COST_GBP,
        "rows": rows,
    }

