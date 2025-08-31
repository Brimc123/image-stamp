# main.py
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

app = FastAPI()

# Simple health check for Render
@app.get("/health")
def health() -> PlainTextResponse:
    return PlainTextResponse("ok")

# --- Embedded Billing Page (no file I/O, so no 500 from missing file) ---
BILLING_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Billing</title>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; }
    h1 { margin: 0 0 16px 0; }
    .btn { display:inline-block; padding:10px 14px; border:1px solid #333; border-radius:6px; cursor:pointer; }
    .btn:hover { background:#f5f5f5; }
    table { border-collapse: collapse; width: 100%; margin-top: 12px; }
    th, td { border: 1px solid #ddd; padding: 10px; text-align:left; }
    th { background:#f7f7f7; }
    .muted { color:#666; font-size: 14px; margin-top:18px; }
  </style>
</head>
<body>
  <a href="/" style="text-decoration:none;">Back</a>
  <h1>Billing</h1>

  <p>Credits: <strong>0</strong> &middot; Price: £10/credit &middot; Minimum top-up: 5 credits (£50)</p>

  <button id="topup" class="btn">Top up 5 credits (£50)</button>

  <h2 style="margin-top:28px;">Recent Top-ups</h2>
  <table>
    <thead><tr><th>When</th><th>Credits</th><th>Charged</th></tr></thead>
    <tbody><tr><td colspan="3">No top-ups yet</td></tr></tbody>
  </table>

  <h2 style="margin-top:28px;">Recent Usage</h2>
  <table>
    <thead><tr><th>When</th><th>Action</th><th>Credits Δ</th></tr></thead>
    <tbody><tr><td colspan="3">No usage yet</td></tr></tbody>
  </table>

  <p class="muted">This page uses an embedded template to avoid file path issues.</p>

  <script>
    document.getElementById('topup').addEventListener('click', async () => {
      try {
        const res = await fetch('/api/ping');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        alert(`Backend says ok=${data.ok}, message="${data.message}"`);
      } catch (e) {
        alert('Top-up test call failed: ' + e);
        console.error(e);
      }
    });
  </script>
</body>
</html>
"""

@app.get("/billing", response_class=HTMLResponse)
async def billing() -> HTMLResponse:
    # Serve the embedded HTML directly
    return HTMLResponse(BILLING_HTML)

# Tiny test API the button calls
@app.get("/api/ping")
async def api_ping() -> JSONResponse:
    return JSONResponse({"ok": True, "message": "pong"})
