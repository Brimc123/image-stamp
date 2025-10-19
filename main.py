# ========================================
# INSTRUCTIONS: Add these imports and routes to your main.py
# ========================================

# 1. UPDATE THE IMPORT (around line 29-32)
# FIND THIS:
from retrofit_tool import (
    get_retrofit_tool_page,
    post_retrofit_process,
    get_retrofit_questions_page,
    post_retrofit_answer,
    post_retrofit_complete
)

# REPLACE WITH THIS:
from retrofit_tool import (
    get_retrofit_tool_page,
    post_retrofit_process,
    get_calc_upload_page,
    post_retrofit_calcs,
    get_retrofit_questions_page,
    post_retrofit_answer,
    post_retrofit_complete
)


# 2. ADD THESE NEW ROUTES (around line 313-325)
# KEEP YOUR EXISTING ROUTES AND ADD THESE 2 NEW ONES:

@app.get("/tool/retrofit/calcs")
def retrofit_calc_upload(request: Request):
    return get_calc_upload_page(request)

@app.post("/api/retrofit-calcs")
async def process_retrofit_calcs(request: Request):
    return await post_retrofit_calcs(request)


# ========================================
# ALL YOUR ROUTES SHOULD NOW BE:
# 
# @app.get("/tool/retrofit")  ← Upload page
# @app.post("/api/retrofit-process")  ← Process PDFs
# @app.get("/tool/retrofit/calcs")  ← NEW! Calc upload (conditional)
# @app.post("/api/retrofit-calcs")  ← NEW! Process calcs
# @app.get("/tool/retrofit/questions")  ← Questions
# @app.post("/api/retrofit-answer")  ← Save answers
# @app.post("/api/retrofit-complete")  ← Generate PDF
# ========================================
