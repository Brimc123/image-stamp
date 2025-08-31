# main.py
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

app = FastAPI()

@app.get("/health")
def health() -> PlainTextResponse:
    return PlainTextResponse("ok")

# ----------------------- BILLING PAGE (EMBEDDED) -----------------------
BILLING_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Billing · Autodate</title>
  <style>
    :root{
      --bg:#f6f7fb;
      --card:#ffffff;
      --text:#111827;
      --muted:#6b7280;
      --border:#e5e7eb;
      --accent:#4f46e5;       /* indigo-600 */
      --accent-700:#3730a3;   /* indigo-800 */
      --success:#059669;      /* emerald-600 */
      --shadow:0 10px 20px rgba(0,0,0,.06);
      --radius:16px;
      --radius-sm:10px;
    }
    @media (prefers-color-scheme: dark) {
      :root{
        --bg:#0f1221;
        --card:#12162b;
        --text:#e5e7eb;
        --muted:#9ca3af;
        --border:#232743;
        --shadow:0 10px 22px rgba(0,0,0,.35);
      }
    }
    *{box-sizing:border-box}
    html,body{height:100%}
    body{
      margin:0;
      background:var(--bg);
      color:var(--text);
      font:16px/1.45 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
    }

    /* layout */
    .container{max-width:1040px;margin:32px auto;padding:0 20px}
    .header{
      display:flex;justify-content:space-between;align-items:center;margin-bottom:18px
    }
    .brand{display:flex;gap:10px;align-items:center}
    .logo{
      width:36px;height:36px;border-radius:10px;
      background:linear-gradient(135deg,var(--accent),#7c3aed);
      box-shadow:var(--shadow)
    }
    .title{font-weight:700;font-size:20px}
    a.back{color:var(--muted);text-decoration:none}
    a.back:hover{color:var(--text)}

    /* cards */
    .grid{display:grid;grid-template-columns:1fr;gap:18px}
    @media(min-width:900px){ .grid{grid-template-columns: 1.1fr .9fr} }
    .card{
      background:var(--card); border:1px solid var(--border);
      border-radius:var(--radius); box-shadow:var(--shadow);
      padding:18px;
    }
    .card h2{margin:0 0 10px 0;font-size:18px}
    .muted{color:var(--muted)}

    /* balance strip */
    .balance{
      display:flex;justify-content:space-between;align-items:center;gap:16px;
      background:linear-gradient(180deg,rgba(79,70,229,.08),transparent);
      border-radius:var(--radius-sm); padding:14px 16px; border:1px dashed var(--border);
      margin-bottom:14px;
    }
    .kpis{display:flex;gap:18px;flex-wrap:wrap}
    .kpi .label{color:var(--muted);font-size:13px}
    .kpi .value{font-weight:700;font-size:22px}

    /* button */
    .btn{
      appearance:none;border:0;cursor:pointer;font-weight:600;
      background:linear-gradient(135deg,var(--accent),var(--accent-700));
      color:#fff; padding:12px 16px;border-radius:12px;
      box-shadow:0 8px 16px rgba(79,70,229,.35); transition:transform .06s ease, box-shadow .2s ease;
    }
    .btn:hover{transform:translateY(-1px);box-shadow:0 12px 22px rgba(79,70,229,.4)}
    .btn:active{transform:translateY(0)}

    /* tables */
    table{width:100%;border-collapse:separate;border-spacing:0;margin-top:6px}
    thead th{
      text-align:left;font-size:13px;color:var(--muted);font-weight:600;
      padding:12px;border-bottom:1px solid var(--border);
    }
    tbody td{padding:14px 12px;border-bottom:1px solid var(--border)}
    tbody tr:last-child td{border-bottom:0}
    .empty{
      text-align:center;color:var(--muted);padding:28px;border:1px dashed var(--border);
      border-radius:12px;margin-top:8px
    }

    /* toast */
    #toast{
      position:fixed; inset:auto 24px 24px auto; z-index:9999; display:none;
      background:var(--card); border:1px solid var(--border); color:var(--text);
      padding:12px 14px; border-radius:12px; box-shadow:var(--shadow);
    }
    #toast.ok { border-left:6px solid var(--success); padding-left:10px }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <a href="/" class="back">← Back</a>
      <div class="brand">
        <div class="logo" aria-hidden="true"></div>
        <div class="title">Autodate · Billing</div>
      </div>
    </div>

    <div class="grid">
      <!-- LEFT: activity -->
      <section class="card">
        <div class="balance">
          <div class="kpis">
            <div class="kpi"><div class="label">Credits</div><div class="value" id="credits">0</div></div>
            <div class="kpi"><div class="label">Price</div><div class="value">£10 / credit</div></div>
            <div class="kpi"><div class="label">Minimum top-up</div><div class="value">5 credits (£50)</div></div>
          </div>
          <button class="btn" id="topup">Top up 5 credits (£50)</button>
        </div>

        <h2>Recent Top-ups</h2>
        <div class="empty" id="no-topups">No top-ups yet</div>
        <table aria-label="Recent top-ups" style="display:none" id="topups-table">
          <thead><tr><th>When</th><th>Credits</th><th>Charged</th></tr></thead>
          <tbody id="topups-body"></tbody>
        </table>

        <h2 style="margin-top:18px">Recent Usage</h2>
        <div class="empty" id="no-usage">No usage yet</div>
        <table aria-label="Recent usage" style="display:none" id="usage-table">
          <thead><tr><th>When</th><th>Action</th><th>Credits Δ</th></tr></thead>
          <tbody id="usage-body"></tbody>
        </table>

        <p class="muted" style="margin-top:14px">Beautiful, embedded UI (no external files). Fully responsive and ready for wiring to real data.</p>
      </section>

      <!-- RIGHT: summary -->
      <aside class="card">
        <h2>Account Summary</h2>
        <ul class="muted" style="padding-left:18px; margin:10px 0 0 0;">
          <li>Plan: <strong>Pay-as-you-go</strong></li>
          <li>Billing currency: <strong>GBP (£)</strong></li>
          <li>Invoices: <a href="#" class="muted" onclick="alert('Coming soon'); return false;">view history</a></li>
          <li>Support: <a href="mailto:support@autodate.co.uk">support@autodate.co.uk</a></li>
        </ul>
      </aside>
    </div>
  </div>

  <div id="toast" role="status" aria-live="polite"></div>

  <script>
    // Simple toast helper
    const toast = (msg, ok=true) => {
      const el = document.getElementById('toast');
      el.className = ok ? 'ok' : '';
      el.textContent = msg;
      el.style.display = 'block';
      setTimeout(()=> el.style.display = 'none', 2500);
    };

    // Demo handler – calls backend to prove connectivity
    document.getElementById('topup').addEventListener('click', async (e) => {
      const btn = e.currentTarget;
      const prev = btn.textContent;
      btn.disabled = true; btn.textContent = 'Processing…';
      try {
        const res = await fetch('/api/ping');
        const data = await res.json();
        if (!res.ok) throw new Error('HTTP ' + res.status);
        toast('Top-up test successful: ' + data.message, true);
      } catch(err){
        console.error(err);
        toast('Top-up test failed', false);
      } finally {
        btn.disabled = false; btn.textContent = prev;
      }
    });
  </script>
</body>
</html>
"""

@app.get("/billing", response_class=HTMLResponse)
async def billing() -> HTMLResponse:
    return HTMLResponse(BILLING_HTML)

@app.get("/api/ping")
async def api_ping() -> JSONResponse:
    # still a simple test endpoint – we’ll wire real top-ups later
    return JSONResponse({"ok": True, "message": "pong"})
# -----------------------------------------------------------------------
