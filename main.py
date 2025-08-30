import os
from typing import List
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from pathlib import Path
import tempfile

# local modules
from processing import parse_times, process_images_paths
from auth import router as auth_router, get_current_user, db_decrement_credit, db_log_usage

APP_DIR = Path(__file__).resolve().parent

def _read_text(filename: str) -> str:
    p = APP_DIR / filename
    try:
        return p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"{filename} not found"

app = FastAPI(title="Time & Date Stamp")

# ---- CORS: read allowlist from env -----------------------------------------
_raw = os.getenv("ALLOWED_ORIGINS", "")
allowed_origins = [o.strip() for o in _raw.split(",") if o.strip()]
if not allowed_origins:
    # safe defaults (prod + local dev). edit if you like.
    allowed_origins = [
        "https://image-stamp.onrender.com",
        "https://autodate.co.uk",
        "https://www.autodate.co.uk",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# auth routes
app.include_router(auth_router, prefix="/auth")

# ---- pages ------------------------------------------------------------------
@app.get("/health")
def health():
    return {"message": "Time & Date Stamp API is running"}

@app.get("/")
def root():
    return RedirectResponse(url="/app")

@app.get("/app", response_class=HTMLResponse)
def app_page():
    return _read_text("index.html")

@app.get("/billing", response_class=HTMLResponse)
def billing_page():
    return _read_text("billing.html")

# ---- stamp API --------------------------------------------------------------
@app.post("/api/stamp")
async def api_stamp(
    request: Request,
    user: dict = Depends(get_current_user),
    files: List[UploadFile] = File(...),
    date_text: str = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    crop_bottom: int = Form(120),
):
    if not user.get("is_active", False):
        raise HTTPException(status_code=403, detail="Account locked. Contact support.")
    if not files:
        raise HTTPException(status_code=400, detail="No files received.")
    if int(user["credits"]) < 1:
        raise HTTPException(status_code=402, detail="No credits left. Please top up.")

    # save uploads to a temp dir and process
    with tempfile.TemporaryDirectory() as tmpd:
        paths = []
        for up in files:
            name = Path(up.filename or "upload.jpg").name
            dest = Path(tmpd) / name
            dest.write_bytes(await up.read())
            paths.append(str(dest))

        out_zip = str(Path(tmpd) / "stamped.zip")
        try:
            process_images_paths(
                paths,
                date_text=date_text.strip(),
                start_time=start_time.strip(),
                end_time=end_time.strip(),
                crop_bottom_px=int(crop_bottom),
                out_zip_path=out_zip,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Processing error: {e}")

        # one credit per stamp action
        uid = int(user["id"])
        db_decrement_credit(uid, 1)
        db_log_usage(uid, -1, "stamp")

        return FileResponse(out_zip, media_type="application/zip", filename="stamped.zip")
