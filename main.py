# main.py
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from security import SecurityMiddleware

APP_ENV = os.getenv("APP_ENV", "development")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")
ALLOW_DEMO_TOPUP = os.getenv("ALLOW_DEMO_TOPUP", "0")
CREDIT_COST_GBP = os.getenv("CREDIT_COST_GBP", "20")

app = FastAPI(title="IMAGE STAMP", version="1.0.0")

# --- Global security middleware ---
app.add_middleware(SecurityMiddleware)

# --- Static front-end (/app) ---
# Expects index.html in the same folder as main.py (adjust path if needed)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML = os.path.join(BASE_DIR, "index.html")
STATIC_DIR = os.path.join(BASE_DIR, "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/app")
async def serve_app():
    if not os.path.isfile(INDEX_HTML):
        return JSONResponse({"error": "index.html not found"}, status_code=404)
    return FileResponse(INDEX_HTML)

# --- Optional health check ---
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "env": APP_ENV,
        "allow_demo_topup": ALLOW_DEMO_TOPUP,
        "credit_cost_gbp": CREDIT_COST_GBP
    }

# --- Include existing routers if present ---
def _maybe_include(module_name: str, router_name: str = "router"):
    try:
        mod = __import__(module_name, fromlist=[router_name])
        router = getattr(mod, router_name)
        app.include_router(router)
        print(f"Included router: {module_name}.{router_name}")
    except Exception as e:
        print(f"Skipping router {module_name}: {e}")

# Try to include your app routers (these are typical names—safe to skip if different)
_maybe_include("auth")        # e.g. /auth/signup, /auth/login, /auth/topup_admin, etc.
_maybe_include("processing")  # e.g. /api/stamp
_maybe_include("report")      # e.g. /report/weekly

# --- Root redirect (optional) ---
@app.get("/")
async def root_redirect():
    return FileResponse(INDEX_HTML) if os.path.isfile(INDEX_HTML) else JSONResponse(
        {"message": "Go to /app"}, status_code=200
    )
