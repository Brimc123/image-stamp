import sqlite3
from config import DB_PATH

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database tables"""
    conn = get_db()
    cur = conn.cursor()
    
    # Users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            credits REAL DEFAULT 0.0,
            is_active INTEGER DEFAULT 1,
            timestamp_tool_access INTEGER DEFAULT 1,
            retrofit_tool_access INTEGER DEFAULT 1
        )
    """)
    
    # Transactions table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            type TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    conn.commit()
    conn.close()

def get_user_by_email(email: str):
    """Get user by email"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cur.fetchone()
    conn.close()
    return row

def create_user(email: str, password: str):
    """Create new user"""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (email, password, credits) VALUES (?, ?, ?)", 
                   (email, password, 0.0))
        conn.commit()
        user_id = cur.lastrowid
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        conn.close()
        return None

def update_user_credits(user_id: int, new_credits: float):
    """Update user credits"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET credits = ? WHERE id = ?", (new_credits, user_id))
    conn.commit()
    conn.close()

def add_transaction(user_id: int, amount: float, transaction_type: str):
    """Add transaction record"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO transactions (user_id, amount, type) VALUES (?, ?, ?)",
               (user_id, amount, transaction_type))
    conn.commit()
    conn.close()

def get_user_transactions(user_id: int):
    """Get all transactions for a user"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC", 
               (user_id,))
    transactions = cur.fetchall()
    conn.close()
    return transactions

def get_all_users():
    """Get all users (admin only)"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users ORDER BY created_at DESC")
    users = cur.fetchall()
    conn.close()
    return users

def update_user_status(user_id: int, is_active: int):
    """Update user active status"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_active = ? WHERE id = ?", (is_active, user_id))
    conn.commit()
    conn.close()

def update_user_tool_access(user_id: int, tool_name: str, access: int):
    """Update user tool access"""
    conn = get_db()
    cur = conn.cursor()
    if tool_name == "timestamp":
        cur.execute("UPDATE users SET timestamp_tool_access = ? WHERE id = ?", (access, user_id))
    elif tool_name == "retrofit":
        cur.execute("UPDATE users SET retrofit_tool_access = ? WHERE id = ?", (access, user_id))
    conn.commit()
    conn.close()

def get_all_transactions():
    """Get all transactions (admin only)"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT t.*, u.email 
        FROM transactions t 
        JOIN users u ON t.user_id = u.id 
        ORDER BY t.created_at DESC
    """)
    transactions = cur.fetchall()
    conn.close()
    return transactions
