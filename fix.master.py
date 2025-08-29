# fix_master.py
import sqlite3, bcrypt

DB = "app.db"
EMAIL = "brimc123@hotmail.com"
PASS  = "Dylan1981!!"
CREDITS = 50

hpw = bcrypt.hashpw(PASS.encode(), bcrypt.gensalt()).decode()

with sqlite3.connect(DB) as conn:
    # ensure users table + columns exist
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE)")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    need = {
        "password":   "TEXT",
        "credits":    "INTEGER NOT NULL DEFAULT 0",
        "is_active":  "INTEGER NOT NULL DEFAULT 1",
        "created_at": "INTEGER NOT NULL DEFAULT (strftime('%s','now'))",
    }
    for col, ddl in need.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")

    # upsert master
    row = conn.execute("SELECT id FROM users WHERE email=?", (EMAIL,)).fetchone()
    if row:
        uid = row[0]
        conn.execute("UPDATE users SET password=?, credits=?, is_active=1 WHERE id=?",
                     (hpw, CREDITS, uid))
        print(f"✅ Updated existing master: {EMAIL} (credits={CREDITS})")
    else:
        conn.execute("INSERT INTO users(email,password,credits,is_active) VALUES(?,?,?,1)",
                     (EMAIL, hpw, CREDITS))
        print(f"✅ Created master: {EMAIL} (credits={CREDITS})")
    conn.commit()
print("Done.")
