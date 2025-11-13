"""
Admin Module - User Management and Reports
"""

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from database import (
    get_all_users, get_user_by_id, get_all_usage_logs,
    get_weekly_report, update_user_max_balance,
    update_user_tool_access, set_user_credits, add_transaction,
    delete_user
)

templates = Jinja2Templates(directory="templates")


async def get_admin_dashboard(request: Request):
    """Admin dashboard - user management and reports."""
    # Get current Monday
    today = datetime.now()
    current_monday = today - timedelta(days=today.weekday())
    current_monday_str = current_monday.strftime("%Y-%m-%d")
    
    # Get all users
    users = get_all_users()
    
    # Get recent usage logs (last 50)
    all_logs = get_all_usage_logs()
    all_logs.sort(key=lambda x: x["timestamp"], reverse=True)
    recent_logs = all_logs[:50]
    
    # Add username to logs
    for log in recent_logs:
        user_data = get_user_by_id(log["user_id"])
        log["username"] = user_data["username"] if user_data else "Unknown"
    
    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "users": users,
        "recent_logs": recent_logs,
        "current_monday": current_monday_str
    })


async def get_admin_weekly_report(request: Request, start_date: str = None):
    """Generate weekly report starting from specified Monday."""
    # Parse start date or use current Monday
    if start_date:
        monday_date = datetime.fromisoformat(start_date)
    else:
        today = datetime.now()
        monday_date = today - timedelta(days=today.weekday())
    
    # Get weekly report
    weekly_report = get_weekly_report(monday_date)
    
    # Get all users
    users = get_all_users()
    
    # Get recent logs
    all_logs = get_all_usage_logs()
    all_logs.sort(key=lambda x: x["timestamp"], reverse=True)
    recent_logs = all_logs[:50]
    
    for log in recent_logs:
        user_data = get_user_by_id(log["user_id"])
        log["username"] = user_data["username"] if user_data else "Unknown"
    
    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "users": users,
        "recent_logs": recent_logs,
        "weekly_report": weekly_report,
        "current_monday": monday_date.strftime("%Y-%m-%d")
    })


async def get_admin_user_edit(request: Request, user_id: int):
    """Edit user page."""
    user = get_user_by_id(user_id)
    if not user:
        return HTMLResponse(content="<h1>User not found</h1>", status_code=404)
    
    return templates.TemplateResponse("admin_user_edit.html", {
        "request": request,
        "user": user
    })


async def post_admin_user_edit(request: Request, user_id: int, user_row: dict):
    """Handle user edit form submission."""
    user = get_user_by_id(user_id)
    if not user:
        return HTMLResponse(content="<h1>User not found</h1>", status_code=404)
    
    form_data = await request.form()
    
    # Update max balance
    max_balance = float(form_data.get("max_balance", 100))
    update_user_max_balance(user_id, max_balance)
    
    # Update tool access
    timestamp_access = "timestamp_tool_access" in form_data
    retrofit_access = "retrofit_tool_access" in form_data
    ats_access = "ats_tool_access" in form_data
    adf_access = "adf_tool_access" in form_data
    
    update_user_tool_access(user_id, "timestamp", timestamp_access)
    update_user_tool_access(user_id, "retrofit", retrofit_access)
    update_user_tool_access(user_id, "ats", ats_access)
    update_user_tool_access(user_id, "adf", adf_access)
    
    # Adjust credits if specified
    credit_adjustment = float(form_data.get("credit_adjustment", 0))
    if credit_adjustment != 0:
        new_balance = user["credits"] + credit_adjustment
        # Enforce max balance (unless it's admin)
        if user_id != 1 and new_balance > max_balance:
            new_balance = max_balance
        set_user_credits(user_id, new_balance)
        
        # Log transaction
        description = f"Admin adjustment by {user_row['username']}"
        add_transaction(user_id, credit_adjustment, description)
    
    return RedirectResponse(url="/admin", status_code=303)


async def post_admin_user_delete(request: Request, user_id: int):
    """Handle user deletion."""
    # Prevent deleting admin account
    if user_id == 1:
        return HTMLResponse(
            content="<h1>Error: Cannot delete admin account</h1>",
            status_code=403
        )
    
    success = delete_user(user_id)
    
    if success:
        return RedirectResponse(url="/admin?deleted=success", status_code=303)
    else:
        return HTMLResponse(
            content="<h1>Error: User not found or could not be deleted</h1>",
            status_code=404
        )
