import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Project root
ROOT_DIR = Path(__file__).parent.parent

# Counties to monitor
COUNTIES = [
    c.strip().lower()
    for c in os.getenv("COUNTIES", "").split(",")
    if c.strip()
]

# Price filters
MIN_PRICE = int(os.getenv("MIN_PRICE", "0") or "0")
MAX_PRICE = int(os.getenv("MAX_PRICE", "0") or "0")  # 0 = no limit

# Property types to monitor
PROPERTY_TYPES = [
    t.strip().lower()
    for t in os.getenv("PROPERTY_TYPES", "all").split(",")
    if t.strip()
]

# Zip codes to filter
ZIP_CODES = [
    z.strip()
    for z in os.getenv("ZIP_CODES", "").split(",")
    if z.strip()
]

# Keywords to search
KEYWORDS = [
    k.strip().lower()
    for k in os.getenv("KEYWORDS", "").split(",")
    if k.strip()
]

# Database
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", ROOT_DIR / "data" / "properties.db"))

# Notifications
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Browser
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
SCREENSHOT_ON_NEW = os.getenv("SCREENSHOT_ON_NEW", "true").lower() == "true"
SCREENSHOTS_DIR = ROOT_DIR / "screenshots"

# Ensure directories exist
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# Property type mappings
PROPERTY_TYPE_LABELS = {
    "residential": "Residential",
    "commercial": "Commercial",
    "land": "Vacant Land",
    "foreclosure": "Foreclosure",
    "lien": "Tax Lien",
    "transfer": "Transfer/Deed",
    "all": "All Types",
}
