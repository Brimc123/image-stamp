import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List

DB_FILE = "database.json"

def read_db():
    """Read the entire database."""
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"users": [], "transactions": [], "usage_logs": []}

def write_db(data):
    """Write data to the database."""
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_user_by_id(user_id: int) -> Optional[Dict]:
    """Get user by ID."""
    db = read_db()
    for user in db["users"]:
        if user["id"] == user_id:
            return user
    return None

def get_user_by_username(username: str) -> Optional[Dict]:
    """Get user by username."""
    db = read_db()
    for user in db["users"]:
        if user["username"] == username:
            return user
    return None

def set_user_credits(user_id: int, new_balance: float):
    """Update user credits."""
    db = read_db()
    for user in db["users"]:
        if user["id"] == user_id:
            user["credits"] = new_balance
            write_db(db)
            return True
    return False

def add_transaction(user_id: int, amount: float, description: str):
    """Add a transaction record."""
    db = read_db()
    new_id = max([t["id"] for t in db["transactions"]], default=0) + 1
    transaction = {
        "id": new_id,
        "user_id": user_id,
        "amount": amount,
        "description": description,
        "timestamp": datetime.now().isoformat()
    }
    db["transactions"].append(transaction)
    write_db(db)
    return transaction

def log_usage(user_id: int, tool_name: str, cost: float, details: str = ""):
    """Log tool usage."""
    db = read_db()
    if "usage_logs" not in db:
        db["usage_logs"] = []
    new_id = max([log["id"] for log in db["usage_logs"]], default=0) + 1
    usage_log = {
        "id": new_id,
        "user_id": user_id,
        "tool_name": tool_name,
        "cost": cost,
        "details": details,
        "timestamp": datetime.now().isoformat()
    }
    db["usage_logs"].append(usage_log)
    write_db(db)
    return usage_log

def get_all_usage_logs(start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict]:
    """Get all usage logs, optionally filtered by date range."""
    db = read_db()
    logs = db.get("usage_logs", [])
    
    if start_date:
        logs = [log for log in logs if log["timestamp"] >= start_date]
    if end_date:
        logs = [log for log in logs if log["timestamp"] <= end_date]
    
    return logs

def get_weekly_report(monday_date: Optional[datetime] = None) -> Dict:
    """Generate weekly report starting from Monday."""
    if monday_date is None:
        today = datetime.now()
        monday_date = today - timedelta(days=today.weekday())
    
    if monday_date.weekday() != 0:
        monday_date = monday_date - timedelta(days=monday_date.weekday())
    
    start_date = monday_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = start_date + timedelta(days=7)
    
    start_iso = start_date.isoformat()
    end_iso = end_date.isoformat()
    
    logs = get_all_usage_logs(start_iso, end_iso)
    
    user_summary = {}
    
    for log in logs:
        user_id = log["user_id"]
        if user_id not in user_summary:
            user = get_user_by_id(user_id)
            user_summary[user_id] = {
                "username": user["username"] if user else "Unknown",
                "total_spent": 0.0,
                "tool_usage": {},
                "usage_count": 0
            }
        
        user_summary[user_id]["total_spent"] += log["cost"]
        user_summary[user_id]["usage_count"] += 1
        
        tool = log["tool_name"]
        if tool not in user_summary[user_id]["tool_usage"]:
            user_summary[user_id]["tool_usage"][tool] = {"count": 0, "total": 0.0}
        
        user_summary[user_id]["tool_usage"][tool]["count"] += 1
        user_summary[user_id]["tool_usage"][tool]["total"] += log["cost"]
    
    return {
        "start_date": start_iso,
        "end_date": end_iso,
        "user_summary": user_summary,
        "total_revenue": sum(u["total_spent"] for u in user_summary.values())
    }

def is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    user = get_user_by_id(user_id)
    return user and user.get("is_admin") == 1

def get_all_users() -> List[Dict]:
    """Get all users."""
    db = read_db()
    return db["users"]

def update_user_tool_access(user_id: int, tool_name: str, has_access: bool):
    """Update tool access for a user."""
    db = read_db()
    for user in db["users"]:
        if user["id"] == user_id:
            access_field = f"{tool_name}_tool_access"
            user[access_field] = 1 if has_access else 0
            write_db(db)
            return True
    return False

def update_user_max_balance(user_id: int, max_balance: float):
    """Update maximum balance for a user."""
    db = read_db()
    for user in db["users"]:
        if user["id"] == user_id:
            user["max_balance"] = max_balance
            write_db(db)
            return True
    return False

def create_user(username: str, password_hash: str, is_admin: int = 0) -> Optional[Dict]:
    """Create a new user."""
    db = read_db()
    
    if get_user_by_username(username):
        return None
    
    new_id = max([u["id"] for u in db["users"]], default=0) + 1
    
    user = {
        "id": new_id,
        "username": username,
        "password_hash": password_hash,
        "is_admin": is_admin,
        "is_active": 1,
        "credits": 0.0,
        "max_balance": 500.0,
        "created_at": datetime.now().isoformat(),
        "timestamp_tool_access": 1,
        "retrofit_tool_access": 1,
        "ats_tool_access": 1,
        "adf_tool_access": 1,
        "sf70_tool_access": 1
    }
    
    db["users"].append(user)
    write_db(db)
    return user

def update_user_credits(user_id: int, new_balance: float):
    """Update user credits."""
    return set_user_credits(user_id, new_balance)

def update_user_status(user_id: int, is_active: int):
    """Update user active status."""
    db = read_db()
    for user in db["users"]:
        if user["id"] == user_id:
            user["is_active"] = is_active
            write_db(db)
            return True
    return False

def get_user_transactions(user_id: int) -> List[Dict]:
    """Get all transactions for a specific user."""
    db = read_db()
    return [t for t in db["transactions"] if t["user_id"] == user_id]

def delete_user(user_id: int) -> bool:
    """Delete a user and all their associated data."""
    # Protect admin account from deletion
    if user_id == 1:
        return False
    
    db = read_db()
    
    # Remove user
    initial_user_count = len(db["users"])
    db["users"] = [u for u in db["users"] if u["id"] != user_id]
    
    # Check if user was actually removed
    if len(db["users"]) == initial_user_count:
        return False  # User not found
    
    # Remove user's transactions
    db["transactions"] = [t for t in db["transactions"] if t["user_id"] != user_id]
    
    # Remove user's usage logs
    if "usage_logs" in db:
        db["usage_logs"] = [log for log in db["usage_logs"] if log["user_id"] != user_id]
    
    write_db(db)
    return True