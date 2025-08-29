# db_fix.py
import sqlite3

DB_FILE = "app.db"

def has_column(conn, table, col):
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    return col in cols

with sqlite3.connect(DB_FILE) as conn:
    # Ensure users table exists (minimal shape)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      email      TEXT NOT NULL UNIQUE
    )
    """)
    conn.commit()

    # Add missing columns
    if not has_column(conn, "users", "credits"):
        conn.execute("ALTER TABLE users ADD COLUMN credits INTEGER NOT NULL DEFAULT 0")
        print("✅ Added column: users.credits")
    if not has_column(conn, "users", "is_active"):
        conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        print("✅ Added column: users.is_active")
    if not has_column(conn, "users", "password"):
        conn.execute("ALTER TABLE users ADD COLUMN password TEXT")
        print("✅ Added column: users.password")
    if not has_column(conn, "users", "created_at"):
        conn.execute("ALTER TABLE users ADD COLUMN created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))")
        print("✅ Added column: users.created_at")

    # Backfill any NULLs just in case
    conn.execute("UPDATE users SET credits=0   WHERE credits   IS NULL")
    conn.execute("UPDATE users SET is_active=1 WHERE is_active IS NULL")

    conn.commit()

print("DB fix complete ✅")
