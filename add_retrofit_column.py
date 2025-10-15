import sqlite3
import os

# Use the same database path as your app
DB_FILE = os.environ.get("DB_FILE", "/var/data/app.db")
DB_PATH = "dev.db"  # local development

def get_db_path():
    return DB_FILE if DB_FILE.startswith("/") else DB_PATH

def add_retrofit_column():
    db_path = get_db_path()
    print(f"Connecting to database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if column already exists
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if "can_use_retrofit_tool" in columns:
        print("✅ Column 'can_use_retrofit_tool' already exists!")
    else:
        print("Adding column 'can_use_retrofit_tool'...")
        cursor.execute("ALTER TABLE users ADD COLUMN can_use_retrofit_tool INTEGER NOT NULL DEFAULT 1")
        conn.commit()
        print("✅ Column added successfully!")
    
    # Show current users
    print("\n📊 Current users:")
    cursor.execute("SELECT email, is_active, can_use_retrofit_tool FROM users")
    for row in cursor.fetchall():
        email, is_active, can_retrofit = row
        status = "✅ Active" if is_active else "❌ Suspended"
        retrofit = "✅ Can use Retrofit" if can_retrofit else "❌ Cannot use Retrofit"
        print(f"  {email}: {status}, {retrofit}")
    
    conn.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    add_retrofit_column()
