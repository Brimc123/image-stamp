"""
Admin Panel - Simple Working Version
"""

from fastapi import Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from auth import require_admin
from database import (
    get_all_users,
    update_user_status,
    set_user_credits,
    add_transaction
)


def get_admin_page(request: Request):
    """Display admin panel"""
    user_row = require_admin(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    users = get_all_users()
    
    users_html = ""
    for user in users:
        status_badge = "🟢 Active" if user.get("is_active", 1) == 1 else "🔴 Suspended"
        admin_badge = "👑 Admin" if user.get("is_admin", 0) == 1 else ""
        
        users_html += f"""
        <tr>
            <td>{user.get("id")}</td>
            <td><strong>{user.get("username")}</strong> {admin_badge}</td>
            <td>£{user.get("credits", 0):.2f}</td>
            <td>{status_badge}</td>
            <td>
                <form method="POST" action="/admin/update-user" style="display: inline;">
                    <input type="hidden" name="user_id" value="{user.get("id")}">
                    <input type="number" step="0.01" name="credits" placeholder="Amount" style="width: 100px;">
                    <button type="submit" name="action" value="add_credits">Add</button>
                    <button type="submit" name="action" value="set_credits">Set</button>
                </form>
                <form method="POST" action="/admin/update-user" style="display: inline;">
                    <input type="hidden" name="user_id" value="{user.get("id")}">
                    {"<button name='action' value='activate'>Activate</button>" if user.get("is_active", 1) == 0 else "<button name='action' value='suspend'>Suspend</button>"}
                </form>
            </td>
        </tr>
        """
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Admin Panel</title>
    <style>
        body {{
            font-family: sans-serif;
            max-width: 1200px;
            margin: 2rem auto;
            padding: 1rem;
            background: #f5f5f5;
        }}
        h1 {{ color: #333; }}
        table {{
            width: 100%;
            background: white;
            border-collapse: collapse;
            margin-top: 1rem;
        }}
        th, td {{
            padding: 1rem;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #667eea;
            color: white;
        }}
        button {{
            padding: 0.5rem 1rem;
            margin: 0 0.25rem;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            background: #667eea;
            color: white;
        }}
        button:hover {{ background: #5568d3; }}
        input {{ padding: 0.5rem; border: 1px solid #ddd; border-radius: 4px; }}
        .back-link {{ display: inline-block; margin-top: 1rem; }}
    </style>
</head>
<body>
    <h1>👑 Admin Panel</h1>
    <a href="/" class="back-link">← Back to Dashboard</a>
    
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Username</th>
                <th>Credits</th>
                <th>Status</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            {users_html}
        </tbody>
    </table>
</body>
</html>
    """
    
    return HTMLResponse(html)


async def post_admin_update_user(
    request: Request,
    user_id: int = Form(...),
    action: str = Form(...),
    credits: float = Form(None)
):
    """Handle admin user updates"""
    user_row = require_admin(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    if action == "add_credits" and credits is not None:
        from database import update_user_credits
        update_user_credits(user_id, credits)
        add_transaction(user_id, credits, "Admin credit adjustment")
    
    elif action == "set_credits" and credits is not None:
        set_user_credits(user_id, credits)
        add_transaction(user_id, 0, f"Admin set credits to £{credits}")
    
    elif action == "suspend":
        update_user_status(user_id, False)
    
    elif action == "activate":
        update_user_status(user_id, True)
    
    return RedirectResponse(url="/admin", status_code=303)
