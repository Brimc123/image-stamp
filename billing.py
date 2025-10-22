from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from database import (
    get_user_transactions,
    update_user_credits,
    add_transaction
)
from auth import require_active_user_row
from config import MINIMUM_TOPUP

def get_billing_page(request: Request):
    """Billing page - view credits and transactions"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    user_id = user_row["id"]
    
    # FIXED: Calculate credits from transactions (same as dashboard)
    try:
        txs = get_user_transactions(user_id)
        # Sum all amounts (TOPUP positive, tool usage negative)
        credits = float(sum(t.get('amount', 0.0) for t in txs))
    except Exception:
        credits = 0.0
    
    # Get transactions
    transactions = get_user_transactions(user_id)
    
    transaction_rows = ""
    for t in transactions:
        try:
            amount = t["amount"]
            trans_type = t["type"]
            created_at = t["created_at"]
        except (KeyError, TypeError):
            continue
        
        color = "#4caf50" if amount > 0 else "#f44336"
        transaction_rows += f"""
            <tr>
                <td>{created_at}</td>
                <td>{trans_type.upper()}</td>
                <td style="color: {color}; font-weight: 600;">£{amount:.2f}</td>
            </tr>
        """
    
    if not transaction_rows:
        transaction_rows = '<tr><td colspan="3" style="text-align: center; color: #999;">No transactions yet</td></tr>'
    
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Billing - AutoDate</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 900px;
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
        .credits-display {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            text-align: center;
            margin-bottom: 30px;
        }}
        .credits-display h2 {{
            font-size: 48px;
            margin-bottom: 10px;
        }}
        .topup-btn {{
            display: inline-block;
            padding: 15px 40px;
            background: #4caf50;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 18px;
            transition: background 0.3s;
            margin-bottom: 30px;
        }}
        .topup-btn:hover {{
            background: #45a049;
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
            margin-top: 20px;
        }}
        .back-btn:hover {{
            background: #764ba2;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Billing & Credits</h1>
        
        <div class="credits-display">
            <h2>£{credits:.2f}</h2>
            <p>Available Credits</p>
        </div>
        
        <a href="/billing/topup" class="topup-btn">Top Up Credits</a>
        
        <h2>Transaction History</h2>
        <table>
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Type</th>
                    <th>Amount</th>
                </tr>
            </thead>
            <tbody>
                {transaction_rows}
            </tbody>
        </table>
        
        <a href="/" class="back-btn">Back to Dashboard</a>
    </div>
</body>
</html>
    """
    return HTMLResponse(html_content)

def get_topup_page(request: Request):
    """Top-up page"""
    user_row = require_active_user_row(request)
    if isinstance(user_row, (RedirectResponse, HTMLResponse)):
        return user_row
    
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Top Up - AutoDate</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            display: flex;
            justify-content: center;
            align-items: center;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
            max-width: 500px;
            width: 100%;
        }}
        h1 {{
            color: #333;
            margin-bottom: 20px;
            font-size: 32px;
            text-align: center;
        }}
        .info-box {{
            background: #e8f4f8;
            border-left: 4px solid #2196F3;
            padding: 15px;
            margin-bottom: 30px;
            border-radius: 5px;
        }}
        .info-box p {{
            color: #555;
            line-height: 1.6;
        }}
        .form-group {{
            margin-bottom: 25px;
        }}
        label {{
            display: block;
            margin-bottom: 10px;
            color: #555;
            font-weight: 600;
        }}
        input {{
            width: 100%;
            padding: 15px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
        }}
        input:focus {{
            outline: none;
            border-color: #667eea;
        }}
        button {{
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #4caf50 0%, #45a049 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }}
        button:hover {{
            transform: translateY(-2px);
        }}
        .back-link {{
            display: block;
            text-align: center;
            margin-top: 20px;
            color: #667eea;
            text-decoration: none;
            font-weight: 600;
        }}
        .back-link:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Top Up Credits</h1>
        
        <div class="info-box">
            <p><strong>Pricing:</strong> £5 per image batch</p>
            <p><strong>Minimum top-up:</strong> £{MINIMUM_TOPUP:.2f}</p>
            <p>Credits are deducted automatically when processing images.</p>
        </div>
        
        <form method="POST" action="/billing/topup">
            <div class="form-group">
                <label>Top-up Amount</label>
                <input type="number" name="amount" min="{MINIMUM_TOPUP:.0f}" step="0.01" value="{MINIMUM_TOPUP:.0f}" required>
            </div>
            <button type="submit">Add Credits</button>
        </form>
        
        <a href="/billing" class="back-link">Back to Billing</a>
    </div>
</body>
</html>
    """
    return HTMLResponse(html_content)

async def post_topup(request: Request, user_row: dict):
    """Process top-up"""
    form = await request.form()
    amount = float(form.get("amount", 0))
    
    if amount < MINIMUM_TOPUP:
        return HTMLResponse(f"""
            <script>
                alert("Minimum top-up is £{MINIMUM_TOPUP:.2f}");
                window.location.href = "/billing/topup";
            </script>
        """)
    
    user_id = user_row["id"]
    
    # Calculate current credits from transactions
    try:
        txs = get_user_transactions(user_id)
        current_credits = float(sum(t.get('amount', 0.0) for t in txs))
    except Exception:
        current_credits = 0.0
    
    # Calculate new balance
    new_credits = current_credits + amount
    
    # Update BOTH: database column AND add transaction
    update_user_credits(user_id, new_credits)
    add_transaction(user_id, amount, "topup")
    
    return HTMLResponse("""
        <script>
            alert("Credits added successfully!");
            window.location.href = "/billing";
        </script>
    """)
