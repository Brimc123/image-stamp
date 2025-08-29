# db_init.py
import sqlite3, os, time

DB_FILE = "app.db"

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  email      TEXT NOT NULL UNIQUE,
  password   TEXT NOT NULL,
  credits    INTEGER NOT NULL DEFAULT 0,
  is_active  INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS sessions (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL,
  token      TEXT NOT NULL UNIQUE,
  expires    INTEGER NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_user  ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token);

CREATE TABLE IF NOT EXISTS usage_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER NOT NULL,
  action      TEXT NOT NULL,             -- e.g. 'stamp', 'login', 'topup'
  bytes_in    INTEGER NOT NULL DEFAULT 0,
  bytes_out   INTEGER NOT NULL DEFAULT 0,
  created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Future-safe: if columns are missing (older db), add them.
"""

def ensure_column(conn, table, col, decl):
    cur = conn.execute(f"PRAGMA table_info({table})")
    cols = {r[1] for r in cur.fetchall()}
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl};")

def main():
    print(f"Using DB file: {os.path.abspath(DB_FILE)}")
    with sqlite3.connect(DB_FILE) as conn:
        conn.executescript(SCHEMA)
        # Minimal migrations for older DBs:
        ensure_column(conn, "users", "created_at", "INTEGER NOT NULL DEFAULT (strftime('%s','now'))")
        ensure_column(conn, "sessions", "created_at", "INTEGER NOT NULL DEFAULT (strftime('%s','now'))")
        ensure_column(conn, "usage_log", "bytes_in", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "usage_log", "bytes_out","INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    print("Database initialized / updated ✅")

if __name__ == "__main__":
    main()
