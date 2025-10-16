# --- Admin Configuration ---
ADMIN_EMAIL = "brimc123@hotmail.com"  # Main admin user
ADMIN_PASSWORD = "Dylan1981!!"  # Admin password

# --- User Helpers ---
def get_user_row_by_email(email: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email=?", (email.lower(),))
    row = cur.fetchone()
    conn.close()
    return row

def is_admin(request: Request) -> bool:
    """Check if current user is admin"""
    email = get_cookie(request, "user_email")
    return email and email.lower() == ADMIN_EMAIL.lower()

def require_admin(request: Request):
    """Require admin access - redirect if not admin"""
    if not is_admin(request):
        return HTMLResponse("""
            <h1>Access Denied</h1>
            <p>You do not have permission to access this page.</p>
            <p><a href="/">← Back to Dashboard</a></p>
        """)
    return None

def require_active_user_row(request: Request):
    email = get_cookie(request, "user_email")
    if not email:
        return RedirectResponse("/login", status_code=302)
    
    row = get_user_row_by_email(email)
    if not row:
        return RedirectResponse("/login", status_code=302)
    
    # Check subscription
    status = row["subscription_status"]
    if status != "active":
        return HTMLResponse("<h1>Subscription Inactive</h1><p>Please subscribe or contact support.</p>")
    
    # Safe access to subscription_end_date
    try:
        end = row["subscription_end_date"]
    except (KeyError, TypeError):
        end = None
    
    if end:
        try:
            end_dt = datetime.fromisoformat(end)
            if datetime.now() > end_dt:
                return HTMLResponse("<h1>Subscription Expired</h1><p>Please renew your subscription.</p>")
        except:
            pass
    
    return row
