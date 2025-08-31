# main.py — full file

import os
from string import Template

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI()

# Sessions (needed by Starlette's SessionMiddleware)
# Safe default so it won't crash if env var missing.
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "change-me"))

# ---- Billing config ----
MIN_TOPUP_CREDITS = int(os.getenv("MIN_TOPUP_CREDITS", "5"))  # minimum bundle size
CREDIT_COST_GBP = int(os.getenv("CREDIT_COST_GBP", "10"))     # price per credit

# ---- Billing HTML (string.Template so { } in CSS is safe) ----
BILLING_HTML_TMPL = Template(r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Billing</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root { --pad: 16px; }
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; }
    h1 { margin: 0 0 12px; }
    a { color: #582; text-decoration: none; }
    a:hover { text-decoration: underline; }
    button { padding: 10px 16px; border-radius: 8px; border: 1px solid #ccc; cursor: pointer; }
    button[disabled] { opacity: .6; cursor: not-allowed; }
    .card { border: 1px solid #eee; border-radius: 10px; margin-top: 18px; }
    .row { display: grid; grid-template-columns: 180px 1fr 160px; padding: var(--pad); }
    .row.head { background: #fafafa; font-weight: 600; }
    .row + .row { border-top: 1px solid #f1f1f1; }
    .muted { color: #666; }
  </style>
</head>
<body>
  <p><a href="/">Back</a></p>
  <h1>Billing</h1>

  <p>
    Credits: <strong>0</strong>
    • Price: £${GBP}/credit
    • Minimum top-up: ${MIN} credits (£${MIN_TOTAL})
  </p>

  <p>
    <button id="buy">Top up ${MIN} credits (£${MIN_TOTAL})</button>
  </p>

  <h3>Recent Top-ups</h3>
  <div class="card">
    <div class="row head"><div>When</div><div>Credits</div><div>Charged</div></div>
    <div class="row"><div class="muted">No top-ups yet</div><div></div><div></div></div>
  </div>

  <h3>Recent Usage</h3>
  <div class="card">
    <div class="row head"><div>When</div><div>Action</div><div>Credits Δ</div></div>
    <div class="row"><div class="muted">No usage yet</div><div></div><div></div></div>
  </div>

  <p class="muted" style="margin-top: 28px;">
    This page uses string.Template to avoid brace issues.
  </p>

  <script>
    (function () {
      // Substituted on the server
      const MIN = ${MIN};

      const buy = document.getElementById('buy');
      if (!buy) return;

      buy.addEventListener('click', async () => {
        buy.disabled = true;
        try {
          const res = await fetch('/api/ping', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ qty: MIN })
          });

          if (!res.ok) {
            const txt = await res.text();
            alert('Ping failed: ' + txt);
            return;
          }

          const data = await res.json();
          alert(`Backend says ok=${data.ok}, qty=${data.qty}`);
        } catch (err) {
          alert('Network error: ' + err);
        } finally {
          buy.disabled = false;
        }
      });
    })();
  </script>
</body>
</html>
""")

# ---- Routes ----

@app.get("/health")
def health() -> PlainTextResponse:
    return PlainTextResponse("ok")

@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    return HTMLResponse("<p>Home. Go to <a href='/billing'>/billing</a></p>")

@app.get("/billing", response_class=HTMLResponse)
def billing_page() -> HTMLResponse:
    html = BILLING_HTML_TMPL.substitute(
        MIN=MIN_TOPUP_CREDITS,
        GBP=CREDIT_COST_GBP,
        MIN_TOTAL=MIN_TOPUP_CREDITS * CREDIT_COST_GBP,
    )
    return HTMLResponse(html)

@app.post("/api/ping")
async def api_ping(request: Request) -> JSONResponse:
    """
    Tiny test endpoint the billing page can call.
    It just echoes qty and returns ok=True.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    qty = body.get("qty", MIN_TOPUP_CREDITS)
    try:
        qty = int(qty)
    except Exception:
        qty = MIN_TOPUP_CREDITS
    qty = max(MIN_TOPUP_CREDITS, qty)
    return JSONResponse({"ok": True, "qty": qty})
