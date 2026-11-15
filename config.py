"""
Central configuration for the Indian Swing Trading Scanner.

Set secrets as environment variables in GitHub Actions.
Do not commit your real API token or Telegram credentials.
"""

import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://eodhd.com/api"
API_TOKEN = os.getenv("EODHD_API_TOKEN", "").strip()

# Portfolio and screening settings
CAPITAL = float(os.getenv("CAPITAL", "100000"))
MIN_STOCK_PRICE = float(os.getenv("MIN_STOCK_PRICE", "200"))
MAX_STOCKS = int(os.getenv("MAX_STOCKS", "500"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.01"))

# Input and alert settings
SYMBOLS_FILE = os.getenv("SYMBOLS_FILE", "symbols.txt")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Basic validation
if CAPITAL <= 0:
    raise ValueError("CAPITAL must be greater than zero.")
if MIN_STOCK_PRICE < 0:
    raise ValueError("MIN_STOCK_PRICE cannot be negative.")
if MAX_STOCKS < 1:
    raise ValueError("MAX_STOCKS must be at least 1.")
if not 0 < RISK_PER_TRADE <= 0.05:
    raise ValueError("RISK_PER_TRADE must be greater than 0 and no more than 0.05.")
