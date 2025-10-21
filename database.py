"""
Database Module - WITH DEBUG LOGGING
Handles all database operations with JSON file storage
"""

import json
import os
from typing import Optional, Dict, List
from datetime import datetime

# Database file path
DB_FILE = "database.json"

# ==================== DATABASE INITIALIZATION ====================

def init_database():
    """Initialize database file if it doesn't exist"""
    if not os.path.exists(DB_FILE):
        print(f"⚠️ Creating new database file: {DB_FILE}")
        default_db = {
            "users": [],
            "transactions": []
        }
        save_database(default_db)
    else:
        print(f"✅ Database file exists: {DB_FILE}")


def load_database() -> Dict:
    """Load database from JSON file"""
    init_database()
    try:
        with open(DB_FILE, 'r') as f:
            db = json.load(f)
            print(f"📂 Loaded database with {len(db.get('users', []))} users")
            return db
    except Exception as e:
        print(f"❌ Error loading database: {e}")
        return {"users": [], "transactions": []}


def save_database(db: Dict):
    """Save database to JSON file"""
    with open(DB_FILE, 'w') as f:
        json.dump(db, f, indent=2)
    print(f"💾 Saved database with {len(db.get('users', []))} users")


# ==================== USER FUNCTIONS ====================

def get_all_users() -> List[Dict]:
    """Get all users from database"""
    db = load_database()
    return db.get("users", [])


def get_user_by_id(user_id: int) -> Optional[Dict]:
    """Get user by ID"""
    db = load_database()
    users = db.get("users", [])
    
    for user in users:
        if user.get("id") == user_id:
            print(f"✅ Found user by ID: {user_id}")
            return user
    
    print(f"❌ User not found by ID: {user_id}")
    return None


def get_user_by_username(username: str) -> Optional[Dict]:
    """Get user by username"""
    print(f"🔍 Searching for user: '{username}'")
    db = load_database()
    users = db.get("users", [])
    
    print(f"📋 Available usernames: {[u.get('username') for u in users]}")
    
    for user in users:
        user_name = user.get("username")
        print(f"  Comparing: '{username}' == '{user_name}' ? {username == user_name}")
        if user_name == username:
            print(f"✅ MATCH FOUND for user: {username}")
            print(f"   Password hash: {user.get('password_hash')[:20]}...")
            return user
    
    print(f"❌ NO MATCH for user: '{username}'")
    return None


def create_user(username: str, password_hash: str, is_admin: bool = False) -> int:
    """Create a new user and return user ID"""
    print(f"➕ Creating new user: {username}")
    db = load_database()
    users = db.get("users", [])
    
    # Generate new user ID
    if users:
        new_id = max(user.get("id", 0) for user in users) + 1
    else:
        new_id = 1
    
    # Create new user
    new_user = {
        "id": new_id,
        "username": username,
        "password_hash": password_hash,
        "is_admin": 1 if is_admin else 0,
        "is_active": 1,
        "credits": 100.0,  # Starting credits
        "created_at": datetime.now().isoformat(),
        "retrofit_tool_access": 1,
        "timestamp_tool_access": 1
    }
    
    users.append(new_user)
    db["users"] = users
    save_database(db)
    
    print(f"✅ User created with ID: {new_id}")
    return new_id


def update_user_status(user_id: int, is_active: bool):
    """Update user active status"""
    db = load_database()
    users = db.get("users", [])
    
    for user in users:
        if user.get("id") == user_id:
            user["is_active"] = 1 if is_active else 0
            break
    
    db["users"] = users
    save_database(db)


def update_user_credits(user_id: int, amount: float):
    """Update user credits (can be positive or negative)"""
    db = load_database()
    users = db.get("users", [])
    
    for user in users:
        if user.get("id") == user_id:
            current_credits = float(user.get("credits", 0.0))
            user["credits"] = current_credits + amount
            break
    
    db["users"] = users
    save_database(db)


def set_user_credits(user_id: int, amount: float):
    """Set user credits to exact amount"""
    db = load_database()
    users = db.get("users", [])
    
    for user in users:
        if user.get("id") == user_id:
            user["credits"] = amount
            break
    
    db["users"] = users
    save_database(db)


def update_user_tool_access(user_id: int, tool_name: str, has_access: bool):
    """Update user's access to a specific tool"""
    db = load_database()
    users = db.get("users", [])
    
    for user in users:
        if user.get("id") == user_id:
            user[f"{tool_name}_access"] = 1 if has_access else 0
            break
    
    db["users"] = users
    save_database(db)


# ==================== TRANSACTION FUNCTIONS ====================

def get_user_transactions(user_id: int) -> List[Dict]:
    """Get all transactions for a user"""
    db = load_database()
    transactions = db.get("transactions", [])
    
    user_transactions = []
    for txn in transactions:
        if txn.get("user_id") == user_id:
            user_transactions.append(txn)
    
    # Sort by date, newest first
    user_transactions.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    
    return user_transactions


def add_transaction(user_id: int, amount: float, description: str):
    """Add a transaction record"""
    db = load_database()
    transactions = db.get("transactions", [])
    
    # Generate new transaction ID
    if transactions:
        new_id = max(txn.get("id", 0) for txn in transactions) + 1
    else:
        new_id = 1
    
    # Create new transaction
    new_txn = {
        "id": new_id,
        "user_id": user_id,
        "amount": amount,
        "description": description,
        "timestamp": datetime.now().isoformat()
    }
    
    transactions.append(new_txn)
    db["transactions"] = transactions
    save_database(db)


# ==================== ADMIN FUNCTIONS ====================

def get_all_transactions() -> List[Dict]:
    """Get all transactions (admin only)"""
    db = load_database()
    transactions = db.get("transactions", [])
    transactions.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return transactions


# ==================== INITIALIZE ON IMPORT ====================

# Initialize database when module is imported
init_database()
