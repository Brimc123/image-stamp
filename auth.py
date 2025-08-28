# auth.py — Auth + Credits + Billing APIs
from fastapi import APIRouter, Request, Response, Form, Depends, Header, HTTPException, Query
from fastapi.responses import Response as FastResponse
from typing import Optional, List
import sqlite3, secrets, os, hashlib
from datetime import datetime, timedelta

router = APIRouter(tags=["auth"])

# ----------------- Config -----------------
DB_PATH = os.path.join(os.path.dirname(__file__), "db.sqlite3")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "changeme_admin_secret")
ALLOW_DEMO_TOPUP = os.environ.get("ALLOW_DEMO_TOPUP", "1") == "1"
CREDIT_COST = int(os.environ.get("CREDIT_COST_GBP", "20"))  # £ per credit
COOKIE_NAME = "sid"

# ----------------- DB helpers -----------------
def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with _db() as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            pw_salt TEXT NOT NULL,
            pw_hash TEXT NOT NULL,
            credits INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions(
            sid TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS usage_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            credits_delta INTEGER NOT NULL,
            kind TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )""")
        conn.commit()

init_db()

# ----------------- Password & users -----------------
def _hash_pw(password: str, salt_hex: str) -> str:
    return hashlib.sha256((salt_hex + password).encode("utf-8")).hexdigest()

def _create_user(email: str, password: str) -> int:
    salt = secrets.token_hex(16)
    h = _hash_pw(password, salt)
    with _db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users(email, pw_salt, pw_hash, credits, is_active, created_at) VALUES(?,?,?,?,?,?)",
            (email, salt, h, 0, 1, datetime.utcnow().isoformat()),
        )
        conn.commit()
        return int(cur.lastrowid)

def _get_user_by_email(email: str) -> Optional[sqlite3.Row]:
    with _db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = ?", (email,))
        return cur.fetchone()

def _get_user_by_id(uid: int) -> Optional[sqlite3.Row]:
    with _db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (uid,))
        return cur.fetchone()

def _verify_pw(user: sqlite3.Row, password: str) -> bool:
    return _hash_pw(password, user["pw_salt"]) == user["pw_hash"]

def _create_session(uid: int) -> str:
    sid = secrets.token_urlsafe(32)
    with _db() as conn:
        conn.execute("INSERT INTO sessions(sid, user_id, created_at) VALUES(?,?,?)",
                     (sid, uid, datetime.utcnow().isoformat()))
        conn.commit()
    return sid

def _user_from_sid(sid: Optional[str]) -> Optional[sqlite3.Row]:
    if not sid:
        return None
    with _db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.sid = ?", (sid,))
        return cur.fetchone()

# ----------------- Credits / usage -----------------
def db_increment_credit(uid: int, amount: int):
    with _db() as conn:
        conn.execute("UPDATE users SET credits = credits + ? WHERE id = ?", (int(amount), uid))
        conn.commit()

def db_decrement_credit(uid: int, amount: int):
    with _db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT credits FROM users WHERE id = ?", (uid,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "User not found")
        if int(row["credits"]) < int(amount):
            raise HTTPException(402, "No credits left.")
        conn.execute("UPDATE users SET credits = credits - ? WHERE id = ?", (int(amount), uid))
        conn.commit()

def db_log_usage(uid: int, delta: int, kind: str):
    with _db() as conn:
        conn.execute(
            "INSERT INTO usage_log(user_id, credits_delta, kind, created_at) VALUES(?,?,?,?)",
            (uid, int(delta), kind, datetime.utcnow().isoformat()),
        )
        conn.commit()

def db_set_active(uid: int, is_active: bool):
    with _db() as conn:
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if is_active else 0, uid))
        conn.commit()

def db_find_user_id(email: str) -> Optional[int]:
    u = _get_user_by_email(email)
    return int(u["id"]) if u else None

def db_weekly_usage_rows() -> List[sqlite3.Row]:
    since = (datetime.utcnow() - timedelta(days=7)).isoformat()
    with _db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT u.email as email, SUM(-ul.credits_delta) as used
            FROM usage_log ul
            JOIN users u ON u.id = ul.user_id
            WHERE ul.credits_delta < 0 AND ul.created_at >= ?
            GROUP BY u.email
            ORDER BY u.email
        """, (since,))
        return cur.fetchall()

# ----------------- Dependencies -----------------
def get_current_user(request: Request) -> dict:
    sid = request.cookies.get(COOKIE_NAME)
    user = _user_from_sid(sid)
    if not user:
        raise HTTPException(401, "Unauthorized")
    return {
        "id": int(user["id"]),
        "email": user["email"],
        "credits": int(user["credits"]),
        "is_active": bool(user["is_active"]),
    }

def is_admin(x_admin_secret: Optional[str] = Header(None)) -> bool:
    if not x_admin_secret or x_admin_secret != ADMIN_SECRET:
        raise HTTPException(401, "Admin auth failed")
    return True

# ----------------- Routes: auth -----------------
@router.post("/auth/signup")
def signup(response: Response, email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    if not email or not password:
        raise HTTPException(422, "Email and password required")
    existing = _get_user_by_email(email)
    if existing:
        if not _verify_pw(existing, password):
            raise HTTPException(400, "User exists with different password")
        uid = int(existing["id"])
    else:
        uid = _create_user(email, password)
    sid = _create_session(uid)
    response.set_cookie(key=COOKIE_NAME, value=sid, httponly=True, samesite="lax", path="/", max_age=60*60*24*30)
    return {"ok": True, "email": email}

@router.post("/auth/login")
def login(response: Response, email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    u = _get_user_by_email(email)
    if not u or not _verify_pw(u, password):
        raise HTTPException(401, "Invalid credentials")
    sid = _create_session(int(u["id"]))
    response.set_cookie(key=COOKIE_NAME, value=sid, httponly=True, samesite="lax", path="/", max_age=60*60*24*30)
    return {"ok": True, "email": email}

@router.post("/auth/logout")
def logout(response: Response, request: Request):
    sid = request.cookies.get(COOKIE_NAME)
    if sid:
        with _db() as conn:
            conn.execute("DELETE FROM sessions WHERE sid = ?", (sid,))
            conn.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}

@router.get("/auth/me")
def me(user=Depends(get_current_user)):
    return {
        "id": user["id"],
        "email": user["email"],
        "credits": user["credits"],
        "is_active": user["is_active"],
        "credit_cost_gbp": CREDIT_COST,
    }

@router.get("/auth/config")
def config():
    return {"allow_demo_topup": ALLOW_DEMO_TOPUP, "credit_cost_gbp": CREDIT_COST}

@router.post("/auth/topup_demo")
def topup_demo(amount: int = Form(...), user=Depends(get_current_user)):
    if not ALLOW_DEMO_TOPUP:
        raise HTTPException(403, "Demo top-up disabled")
    db_increment_credit(user["id"], int(amount))
    db_log_usage(user["id"], int(amount), "demo_topup")
    return {"ok": True, "credits": int(user["credits"]) + int(amount)}

@router.post("/auth/topup_admin")
def topup_admin(email: str = Form(...), amount: int = Form(...), admin_ok: bool = Depends(is_admin)):
    uid = db_find_user_id(email.strip().lower())
    if not uid:
        raise HTTPException(404, "User not found")
    db_increment_credit(uid, int(amount))
    db_log_usage(uid, int(amount), "admin_topup")
    return {"ok": True}

@router.post("/auth/lock_admin")
def lock_admin(email: str = Form(...), is_active: int = Form(...), admin_ok: bool = Depends(is_admin)):
    uid = db_find_user_id(email.strip().lower())
    if not uid:
        raise HTTPException(404, "User not found")
    db_set_active(uid, bool(int(is_active)))
    return {"ok": True}

# ----------------- Routes: reports & billing -----------------
@router.get("/report/weekly")
def weekly_report(admin_ok: bool = Depends(is_admin)):
    rows = db_weekly_usage_rows()
    import io, csv
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["email", "credits_used", "amount_due_gbp"])
    for r in rows:
        used = int(r["used"] or 0)
        w.writerow([r["email"], used, used * CREDIT_COST])
    return FastResponse(buf.getvalue(), media_type="text/csv")

def _range_iso(start: Optional[str], end: Optional[str]):
    # start/end expected as YYYY-MM-DD; end is inclusive on UI but exclusive in query
    try:
        if start:
            s = datetime.fromisoformat(start).replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            s = datetime.utcnow() - timedelta(days=7)
        if end:
            e = datetime.fromisoformat(end).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        else:
            e = datetime.utcnow() + timedelta(days=1)
    except Exception:
        raise HTTPException(422, "Invalid date format; use YYYY-MM-DD")
    return s.isoformat(), e.isoformat()

@router.get("/billing/data")
def billing_data(start: Optional[str] = Query(None), end: Optional[str] = Query(None), user=Depends(get_current_user)):
    s,e = _range_iso(start,end)
    with _db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT created_at, credits_delta, kind
            FROM usage_log
            WHERE user_id=? AND created_at >= ? AND created_at < ? AND credits_delta < 0
            ORDER BY created_at ASC
        """, (user["id"], s, e))
        rows = cur.fetchall()
    items = [{"created_at": r["created_at"], "credits_delta": int(r["credits_delta"]), "kind": r["kind"]} for r in rows]
    used = -sum(int(r["credits_delta"]) for r in rows)
    return {
        "email": user["email"],
        "start": (start or s[:10]),
        "end": (end or (datetime.fromisoformat(e)-timedelta(days=1)).date().isoformat()),
        "rate_gbp": CREDIT_COST,
        "credits_used": used,
        "amount_due_gbp": used * CREDIT_COST,
        "items": items,
    }

@router.get("/billing/csv")
def billing_csv(start: Optional[str] = Query(None), end: Optional[str] = Query(None), user=Depends(get_current_user)):
    s,e = _range_iso(start,end)
    with _db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT created_at, credits_delta, kind
            FROM usage_log
            WHERE user_id=? AND created_at >= ? AND created_at < ? AND credits_delta < 0
            ORDER BY created_at ASC
        """, (user["id"], s, e))
        rows = cur.fetchall()
    import io, csv
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["email", user["email"]])
    w.writerow(["period_start", s])
    w.writerow(["period_end", e])
    w.writerow(["rate_gbp", CREDIT_COST])
    w.writerow([])
    w.writerow(["created_at_utc","type","credits_used","line_amount_gbp"])
    total=0
    for r in rows:
        used = -int(r["credits_delta"])
        amt = used * CREDIT_COST
        w.writerow([r["created_at"], r["kind"], used, amt])
        total += amt
    w.writerow([])
    w.writerow(["total_due_gbp", total])
    out = buf.getvalue()
    return FastResponse(out, media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="billing_{(start or s[:10])}_to_{(end or e[:10])}.csv"'})

@router.get("/billing/admin")
def billing_admin(start: Optional[str] = Query(None), end: Optional[str] = Query(None), admin_ok: bool = Depends(is_admin)):
    s,e = _range_iso(start,end)
    with _db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT u.email AS email, SUM(-ul.credits_delta) AS used
            FROM usage_log ul
            JOIN users u ON u.id=ul.user_id
            WHERE ul.credits_delta < 0 AND ul.created_at >= ? AND ul.created_at < ?
            GROUP BY u.email
            ORDER BY u.email
        """, (s,e))
        rows = cur.fetchall()
    data = [{"email": r["email"], "credits_used": int(r["used"] or 0), "amount_due_gbp": int(r["used"] or 0) * CREDIT_COST} for r in rows]
    return {"rate_gbp": CREDIT_COST, "rows": data}

@router.get("/billing/admin_csv")
def billing_admin_csv(start: Optional[str] = Query(None), end: Optional[str] = Query(None), admin_ok: bool = Depends(is_admin)):
    s,e = _range_iso(start,end)
    with _db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT u.email AS email, SUM(-ul.credits_delta) AS used
            FROM usage_log ul
            JOIN users u ON u.id=ul.user_id
            WHERE ul.credits_delta < 0 AND ul.created_at >= ? AND ul.created_at < ?
            GROUP BY u.email
            ORDER BY u.email
        """, (s,e))
        rows = cur.fetchall()
    import io, csv
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["email","credits_used","amount_due_gbp","rate_gbp"])
    for r in rows:
        used = int(r["used"] or 0)
        w.writerow([r["email"], used, used*CREDIT_COST, CREDIT_COST])
    return FastResponse(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="org_billing_{(start or s[:10])}_to_{(end or e[:10])}.csv"'})
