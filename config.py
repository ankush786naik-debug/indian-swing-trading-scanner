
import os
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv(
    "TEJ_API_BASE_URL",
    "https://api.tejhq.dev"
).rstrip("/")

API_KEY = os.getenv("TEJ_API_KEY", "").strip()

DEFAULT_EXCHANGE = os.getenv(
    "DEFAULT_EXCHANGE",
    "nse"
).lower()

REQUEST_TIMEOUT = int(
    os.getenv("REQUEST_TIMEOUT", "30")
)
