from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from database import (
    get_all_users,
    get_all_transactions,
    update_user_status,
    update_user_tool_access
)
from auth import require_active_user_row, is_admin

def get_admin_panel(request: Request):
    """Admin panel - manage users"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    # Check if user is admin
    if not is_admin(request):
        return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Access Denied</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .container {
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 10px 25px rgba(0,0,0,0.2);
                        text-align: center;
                        max-width: 400px;
                    }
                    h1 { color: #e74c3c; margin-bottom: 20px; }
                    p { color: #555; margin-bottom: 30px; }
                    a {
                        display: inline-block;
                        padding: 12px 30px;
                        background: #667eea;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        transition: background 0.3s;
                    }
                    a:hover { background: #764ba2; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Access Denied</h1>
                    <p>You do not have permission to access the admin panel.</p>
                    <a href="/">Back to Dashboard</a>
                </div>
            </body>
            </html>
        """)
    
    # Get all users
    users = get_all_users()
    
    user_rows_html = ""
    for u in users:
        try:
            user_id = u["id"]
            email = u["email"]
            credits = u["credits"]
            is_active = u["is_active"]
            timestamp_access = u["timestamp_tool_access"]
            retrofit_access = u["retrofit_tool_access"]
        except (KeyError, TypeError):
            continue
        
        status_color = "#4caf50" if is_active == 1 else "#f44336"
        status_text = "Active" if is_active == 1 else "Suspended"
        toggle_text = "Suspend" if is_active == 1 else "Activate"
        
        timestamp_badge = "Timestamp" if timestamp_access == 1 else "No Timestamp"
        timestamp_color = "#4caf50" if timestamp_access == 1 else "#f44336"
        
        retrofit_badge = "Retrofit" if retrofit_access == 1 else "No Retrofit"
        retrofit_color = "#4caf50" if retrofit_access == 1 else "#f44336"
        
        user_rows_html += f"""
            <tr>
                <td>{email}</td>
                <td>£{credits:.2f}</td>
                <td><span style="color: {status_color}; font-weight: 600;">{status_text}</span></td>
                <td>
                    <span style="background: {timestamp_color}; color: white; padding: 5px 10px; border-radius: 5px; font-size: 12px; margin-right: 5px;">{timestamp_badge}</span>
                    <span style="background: {retrofit_color}; color: white; padding: 5px 10px; border-radius: 5px; font-size: 12px;">{retrofit_badge}</span>
                </td>
                <td>
                    <form method="POST" action="/admin/toggle-status" style="display: inline;">
                        <input type="hidden" name="user_id" value="{user_id}">
                        <input type="hidden" name="current_status" value="{is_active}">
                        <button type="submit" style="padding: 8px 15px; background: #ff9800; color: white; border: none; border-radius: 5px; cursor: pointer; margin-right: 5px;">{toggle_text}</button>
                    </form>
                    <form method="POST" action="/admin/toggle-timestamp" style="display: inline;">
                        <input type="hidden" name="user_id" value="{user_id}">
                        <input type="hidden" name="current_access" value="{timestamp_access}">
                        <button type="submit" style="padding: 8px 15px; background: #2196F3; color: white; border: none; border-radius: 5px; cursor: pointer; margin-right: 5px;">Toggle TS</button>
                    </form>
                    <form method="POST" action="/admin/toggle-retrofit" style="display: inline;">
                        <input type="hidden" name="user_id" value="{user_id}">
                        <input type="hidden" name="current_access" value="{retrofit_access}">
                        <button type="submit" style="padding: 8px 15px; background: #9C27B0; color: white; border: none; border-radius: 5px; cursor: pointer;">Toggle RF</button>
                    </form>
                </td>
            </tr>
        """
    
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Admin Panel - AutoDate</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
        }}
        h1 {{
            color: #333;
            margin-bottom: 30px;
            font-size: 32px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        th, td {{
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid #e0e0e0;
        }}
        th {{
            background: #f5f5f5;
            font-weight: 600;
            color: #555;
        }}
        .actions {{
            display: flex;
            gap: 10px;
            margin-bottom: 30px;
        }}
        .actions a {{
            padding: 12px 25px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
        }}
        .actions a:hover {{
            background: #764ba2;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Admin Panel</h1>
        
        <div class="actions">
            <a href="/">Back to Dashboard</a>
            <a href="/admin/billing">View All Billing</a>
        </div>
        
        <h2>User Management</h2>
        <table>
            <thead>
                <tr>
                    <th>Email</th>
                    <th>Credits</th>
                    <th>Status</th>
                    <th>Tool Access</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {user_rows_html}
            </tbody>
        </table>
    </div>
</body>
</html>
    """
    return HTMLResponse(html_content)

def toggle_user_status(request: Request, user_id: int = Form(...), current_status: str = Form(...)):
    """Toggle user active/suspended status"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    if not is_admin(request):
        return HTMLResponse("<script>alert('Access denied!'); window.location.href='/';</script>")
    
    new_status = 0 if int(current_status) == 1 else 1
    update_user_status(user_id, new_status)
    
    return RedirectResponse(url="/admin", status_code=302)

def toggle_timestamp_access(request: Request, user_id: int = Form(...), current_access: str = Form(...)):
    """Toggle timestamp tool access"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    if not is_admin(request):
        return HTMLResponse("<script>alert('Access denied!'); window.location.href='/';</script>")
    
    new_access = 0 if int(current_access) == 1 else 1
    update_user_tool_access(user_id, "timestamp", new_access)
    
    return RedirectResponse(url="/admin", status_code=302)

def toggle_retrofit_access(request: Request, user_id: int = Form(...), current_access: str = Form(...)):
    """Toggle retrofit tool access"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    if not is_admin(request):
        return HTMLResponse("<script>alert('Access denied!'); window.location.href='/';</script>")
    
    new_access = 0 if int(current_access) == 1 else 1
    update_user_tool_access(user_id, "retrofit", new_access)
    
    return RedirectResponse(url="/admin", status_code=302)

def get_admin_billing(request: Request):
    """Admin view all billing"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    if not is_admin(request):
        return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Access Denied</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .container {
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 10px 25px rgba(0,0,0,0.2);
                        text-align: center;
                        max-width: 400px;
                    }
                    h1 { color: #e74c3c; margin-bottom: 20px; }
                    p { color: #555; margin-bottom: 30px; }
                    a {
                        display: inline-block;
                        padding: 12px 30px;
                        background: #667eea;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        transition: background 0.3s;
                    }
                    a:hover { background: #764ba2; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Access Denied</h1>
                    <p>You do not have permission to access admin billing.</p>
                    <a href="/">Back to Dashboard</a>
                </div>
            </body>
            </html>
        """)
    
    transactions = get_all_transactions()
    
    transaction_rows = ""
    for t in transactions:
        try:
            created_at = t["created_at"]
            email = t["email"]
            trans_type = t["type"]
            amount = t["amount"]
        except (KeyError, TypeError):
            continue
        
        color = "#4caf50" if amount > 0 else "#f44336"
        transaction_rows += f"""
            <tr>
                <td>{created_at}</td>
                <td>{email}</td>
                <td>{trans_type.upper()}</td>
                <td style="color: {color}; font-weight: 600;">£{amount:.2f}</td>
            </tr>
        """
    
    if not transaction_rows:
        transaction_rows = '<tr><td colspan="4" style="text-align: center; color: #999;">No transactions yet</td></tr>'
    
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Admin Billing - AutoDate</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
        }}
        h1 {{
            color: #333;
            margin-bottom: 30px;
            font-size: 32px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        th, td {{
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid #e0e0e0;
        }}
        th {{
            background: #f5f5f5;
            font-weight: 600;
            color: #555;
        }}
        .back-btn {{
            display: inline-block;
            padding: 12px 30px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            margin-bottom: 20px;
        }}
        .back-btn:hover {{
            background: #764ba2;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>All Billing Transactions</h1>
        <a href="/admin" class="back-btn">Back to Admin</a>
        
        <table>
            <thead>
                <tr>
                    <th>Date</th>
                    <th>User</th>
                    <th>Type</th>
                    <th>Amount</th>
                </tr>
            </thead>
            <tbody>
                {transaction_rows}
            </tbody>
        </table>
    </div>
</body>
</html>
    """
    return HTMLResponse(html_content)
