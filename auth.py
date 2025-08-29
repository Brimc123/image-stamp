@router.post("/ensure_master")
async def ensure_master(req: Request):
    got = req.headers.get("x-admin-secret","")
    if not ADMIN_SECRET or not got or not hmac.compare_digest(got.encode(), ADMIN_SECRET.encode()):
        raise HTTPException(403, "Forbidden")
    data = await req.json()
    email = (data.get("email") or "").strip().lower()
    pw = data.get("password") or ""
    credits = int(data.get("credits") or 0)
    if not email or not pw:
        raise HTTPException(400, "email and password required")
    hpw = hash_pw(pw)
    with db() as conn:
        row = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if row:
            conn.execute("UPDATE users SET password=?,credits=?,is_active=1 WHERE id=?",
                         (hpw, credits, row[0]))
        else:
            conn.execute("INSERT INTO users(email,password,credits,is_active) VALUES(?,?,?,1)",
                         (email, hpw, credits))
        conn.commit()
    return {"ok": True, "email": email, "credits": credits}
