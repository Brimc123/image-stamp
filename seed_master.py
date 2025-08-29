# seed_master.py
import sqlite3, bcrypt

DB_FILE = "app.db"

MASTER_EMAIL = "brimc123@hotmail.com"
MASTER_PASSWORD = "Dylan1981!!"
START_CREDITS = 50   # you can change this number

hpw = bcrypt.hashpw(MASTER_PASSWORD.encode(), bcrypt.gensalt()).decode()

with sqlite3.connect(DB_FILE) as conn:
    try:
        conn.execute(
            "INSERT INTO users(email,password,credits,is_active) VALUES(?,?,?,1)",
            (MASTER_EMAIL, hpw, START_CREDITS)
        )
        conn.commit()
        print(f"✅ Master user {MASTER_EMAIL} created with {START_CREDITS} credits")
    except Exception as e:
        print("⚠️ Master user already exists or error:", e)
