# Configuration file for AutoDate application

# Admin credentials
ADMIN_EMAIL = "brimc123@hotmail.com"
ADMIN_PASSWORD = "Dylan1981!!"

# Database
DB_PATH = "users.db"

# Pricing
TIMESTAMP_TOOL_COST = 5.0  # £5 per batch
MINIMUM_TOPUP = 50.0  # £50 minimum top-up

# Timestamp Tool Defaults
DEFAULT_FONT_SIZE = 25  # Changed from 30 to 25
DEFAULT_CROP_HEIGHT = 90  # Changed from 60 to 90
TIMESTAMP_PADDING = 30
OUTLINE_WIDTH = 3

# Font paths (in order of preference)
# CHANGED: Using Regular weight fonts instead of Bold
FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # CHANGED: Removed "-Bold"
    "/System/Library/Fonts/Supplemental/Arial.ttf",  # CHANGED: Removed " Bold"
    "C:\\Windows\\Fonts\\arial.ttf",  # CHANGED: Changed from arialbd.ttf to arial.ttf
]
