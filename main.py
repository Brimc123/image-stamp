# main.py
# Time & Date Stamp – FastAPI app with auth + credits + bottom crop stamping
# Includes /app (index.html) and /billing (billing.html) UI routes

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.background import BackgroundTask
from typing import List
import os
import tempfile

from processing import parse_times, process_images_paths
from auth import (
    router as auth_router,
    get_current_user,
    db_decrement_credit,
    db_log_usage,
    CREDIT_COST,
)

app = FastAPI(title="Time & Date Stamp", version="2.1.0")

# Same-origin use; open CORS if you serve the HTML elsewhere
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# include authentication/billing routes
app.include_router(auth_router)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --------------------- UI ---------------------
@app.get("/app", response_class=HTMLResponse, include_in_schema=False)
def app_page():
    index_path = os.path.join(BASE_DIR, "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse("<h2>index.html not found</h2>", status_code=404)
    return HTMLResponse(open(index_path, "r", encoding="utf-8").read())

@app.get("/billing", response_class=HTMLResponse, include_in_schema=False)
def billing_page():
    billing_path = os.path.join(BASE_DIR, "billing.html")
    if not os.path.exists(billing_path):
        return HTMLResponse("<h2>billing.html not found</h2>", status_code=404)
    return HTMLResponse(open(billing_path, "r", encoding="utf-8").read())

@app.get("/")
def root():
    return {"message": "Time & Date Stamp API is running"}

@app.get("/health")
def health():
    return {"status": "ok"}

# ------------------ Stamping API ------------------
@app.post("/api/stamp")
async def api_stamp(
    request: Request,
    files: List[UploadFile] = File(..., description="JPG/PNG files or a single .zip"),
    date_text: str = Form(..., description="dd/mm/yyyy"),
    start_time: str = Form(..., description="HH:MM:SS"),
    end_time: str = Form(..., description="HH:MM:SS"),
    crop_bottom: int = Form(0, description="Pixels to crop from the BOTTOM"),
    user=Depends(get_current_user),  # require login
):
    # 1) account lock?
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Account locked. Please contact support.")

    # 2) credits?
    if int(user["credits"]) <= 0:
        raise HTTPException(status_code=402, detail="No credits left.")

    # 3) Save uploads to temp files (we accept images and/or a single .zip)
    tmp_inputs: List[str] = []
    try:
        for up in files:
            suffix = os.path.splitext(up.filename or "")[1].lower() or ".bin"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp_inputs.append(tmp.name)
            try:
                data = await up.read()
                tmp.write(data)
            finally:
                tmp.close()

        # 4) create temp output zip path
        out_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        out_zip_path = out_zip.name
        out_zip.close()

        # 5) process (crop bottom first, then stamp)
        result_zip = process_images_paths(
            input_paths=tmp_inputs,
            date_text=date_text,
            start_str=start_time,
            end_str=end_time,
            crop_bottom_px=max(0, int(crop_bottom)),
            out_zip_path=out_zip_path,
        )

        # 6) deduct 1 credit per “go” & log usage
        db_decrement_credit(user["id"], 1)
        db_log_usage(user["id"], -1, "stamp")  # consumed 1 credit

        # 7) schedule cleanup of temps and zip after sending
        def _cleanup(paths, zipf):
            import os
            for p in paths:
                if p and os.path.exists(p):
                    try:
                        os.unlink(p)
                    except:
                        pass
            if zipf and os.path.exists(zipf):
                try:
                    os.unlink(zipf)
                except:
                    pass

        return FileResponse(
            result_zip,
            filename="stamped_images.zip",
            media_type="application/zip",
            background=BackgroundTask(_cleanup, tmp_inputs, result_zip),
        )

    except HTTPException:
        # re-raise FastAPI HTTP exceptions
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}")
