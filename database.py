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
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            credits REAL DEFAULT 0.0,
            status TEXT DEFAULT 'active',
            timestamp_tool_access INTEGER DEFAULT 1,
            retrofit_tool_access INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Transactions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    
    conn.commit()
    conn.close()

def get_user_by_email(email: str):
    """Get user by email"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_by_id(user_id: int):
    """Get user by ID - FRESH from database"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def create_user(email: str, password: str):
    """Create new user"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (email, password, credits) VALUES (?, ?, ?)",
            (email, password, 0.0)
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        conn.close()
        return None

def update_user_credits(user_id: int, new_credits: float):
    """Update user credits"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET credits = ? WHERE id = ?",
        (new_credits, user_id)
    )
    conn.commit()
    conn.close()

def add_transaction(user_id: int, amount: float, trans_type: str):
    """Add transaction record"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO transactions (user_id, amount, type) VALUES (?, ?, ?)",
        (user_id, amount, trans_type)
    )
    conn.commit()
    conn.close()

def get_user_transactions(user_id: int):
    """Get user transactions"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    )
    transactions = cursor.fetchall()
    conn.close()
    return [dict(t) for t in transactions]

def get_all_users():
    """Get all users (admin only)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users ORDER BY created_at DESC")
    users = cursor.fetchall()
    conn.close()
    return [dict(u) for u in users]

def get_all_transactions():
    """Get all transactions (admin only)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.*, u.email 
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        ORDER BY t.created_at DESC
    """)
    transactions = cursor.fetchall()
    conn.close()
    return [dict(t) for t in transactions]

def update_user_status(user_id: int, new_status: str):
    """Update user status (active/suspended)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET status = ? WHERE id = ?",
        (new_status, user_id)
    )
    conn.commit()
    conn.close()

def update_user_tool_access(user_id: int, tool_name: str, access: int):
    """Update tool access for user"""
    conn = get_db()
    cursor = conn.cursor()
    
    if tool_name == "timestamp":
        cursor.execute(
            "UPDATE users SET timestamp_tool_access = ? WHERE id = ?",
            (access, user_id)
        )
    elif tool_name == "retrofit":
        cursor.execute(
            "UPDATE users SET retrofit_tool_access = ? WHERE id = ?",
            (access, user_id)
        )
    
    conn.commit()
    conn.close()
