
#!/usr/bin/env python3

import os
import sys
import time
import logging
from datetime import date, timedelta
from collections import Counter

import requests
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()

# CONFIGURATION
API_TOKEN = os.getenv("EODHD_API_TOKEN", "").strip()
BASE_URL = "https://eodhd.com/api"

CAPITAL = float(os.getenv("CAPITAL", "100000"))
MIN_PRICE = float(os.getenv("MIN_STOCK_PRICE", "200"))
MAX_STOCKS = int(os.getenv("MAX_STOCKS", "500"))
RISK_PERCENT = float(os.getenv("RISK_PER_TRADE", "0.01"))

API_DELAY = float(os.getenv("API_MIN_INTERVAL_SEC", "1.1"))
MAX_RETRIES = int(os.getenv("API_MAX_RETRIES", "4"))
MIN_COVERAGE = float(os.getenv("MIN_DATA_COVERAGE", "0.80"))

SYMBOL_FILE = os.getenv("SYMBOLS_FILE", "symbols.txt")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

log = logging.getLogger("scanner")

session = requests.Session()
session.headers.update({"User-Agent": "IndianSwingScanner/2.0"})

last_request = 0.0


def telegram(message):

    if not BOT_TOKEN or not CHAT_ID:
        log.info("Telegram not configured")
        return

    response = session.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": message
        },
        timeout=20
    )

    response.raise_for_status()


def api_get(path, params=None):

    global last_request

    if not API_TOKEN:
        raise RuntimeError("EODHD_API_TOKEN missing")

    query = dict(params or {})
    query.update({
        "api_token": API_TOKEN,
        "fmt": "json"
    })

    url = f"{BASE_URL}/{path}"

    for attempt in range(MAX_RETRIES + 1):

        wait = API_DELAY - (time.monotonic() - last_request)

        if wait > 0:
            time.sleep(wait)

        try:
            response = session.get(
                url,
                params=query,
                timeout=45
            )
            last_request = time.monotonic()

        except requests.RequestException:

            if attempt == MAX_RETRIES:
                raise

            delay = min(2 ** attempt, 30)
            log.warning("Network retry in %s seconds", delay)
            time.sleep(delay)
            continue

        if response.status_code == 429 or response.status_code >= 500:

            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"API unavailable: HTTP {response.status_code}"
                )

            retry_after = response.headers.get("Retry-After")

            try:
                delay = max(float(retry_after), 2)
            except (TypeError, ValueError):
                delay = min(2 ** (attempt + 1), 30)

            log.warning("HTTP %s. Retry in %s seconds",
                        response.status_code, delay)

            time.sleep(delay)
            continue

        if response.status_code in (401, 403):
            raise RuntimeError(
                f"Authentication/subscription error: HTTP {response.status_code}"
            )

        response.raise_for_status()

        data = response.json()

        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(str(data["error"]))

        return data

    raise RuntimeError("API request failed")


def load_symbols():

    if not os.path.exists(SYMBOL_FILE):
        raise FileNotFoundError(SYMBOL_FILE)

    symbols = []

    with open(SYMBOL_FILE, encoding="utf-8") as file:

        for line in file:

            symbol = line.strip().upper()

            if symbol and not symbol.startswith("#"):
                if symbol not in symbols:
                    symbols.append(symbol)

    return symbols[:MAX_STOCKS]


def get_prices(symbol):

    end = date.today()
    start = end - timedelta(days=420)

    data = api_get(
        f"eod/{symbol}",
        {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "period": "d"
        }
    )

    if not isinstance(data, list) or len(data) < 80:
        raise ValueError("Insufficient price history")

    df = pd.DataFrame(data)

    required = [
        "date", "open", "high",
        "low", "close", "volume"
    ]

    if not all(col in df.columns for col in required):
        raise ValueError("Missing OHLCV fields")

    df["date"] = pd.to_datetime(df["date"])

    for col in required[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(
        subset=["close", "high", "low", "volume"]
    )

    return df.sort_values("date").reset_index(drop=True)


def get_fundamentals(symbol):

    data = api_get(f"fundamentals/{symbol}")

    return data if isinstance(data, dict) else {}


def get_number(mapping, *keys):

    for key in keys:

        try:
            value = float(mapping.get(key))

            if np.isfinite(value):
                return value

        except (TypeError, ValueError):
            pass

    return None


def fundamental_score(data):

    highlights = data.get("Highlights") or {}
    valuation = data.get("Valuation") or {}

    score = 0
    reasons = []

    roe = get_number(
        highlights,
        "ReturnOnEquityTTM",
        "ReturnOnEquity"
    )

    margin = get_number(highlights, "ProfitMargin")
    revenue = get_number(highlights, "RevenueGrowth")
    earnings = get_number(highlights, "EarningsGrowth")

    pe = get_number(
        valuation,
        "TrailingPE",
        "ForwardPE"
    )

    pb = get_number(valuation, "PriceBookMRQ")

    if roe is not None and roe >= 15:
        score += 2
        reasons.append("ROE passed")

    if margin is not None and margin >= 10:
        score += 1
        reasons.append("Profit margin passed")

    if revenue is not None and revenue > 0:
        score += 1
        reasons.append("Revenue growth passed")

    if earnings is not None and earnings > 0:
        score += 1
        reasons.append("Earnings growth passed")

    if pe is not None and 0 < pe <= 35:
        score += 1
        reasons.append("P/E passed")

    if pb is not None and 0 < pb <= 6:
        score += 1
        reasons.append("P/B passed")

    return score, reasons


def technical_screen(df):

    close = df["close"]

    sma20 = close.rolling(20).mean()

    delta = close.diff()

    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()

    rs = gain / loss.replace(0, np.nan)

    rsi = 100 - (100 / (1 + rs))

    previous = close.shift(1)

    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - previous).abs(),
        (df["low"] - previous).abs()
    ], axis=1).max(axis=1)

    atr = tr.rolling(14).mean()

    avg_volume = df["volume"].rolling(20).mean()

    support = df["low"].rolling(20).min()

    last = len(df) - 1
    prev = last - 1

    price = float(close.iloc[last])

    if price < MIN_PRICE:
        return None

    values = [
        rsi.iloc[last],
        rsi.iloc[prev],
        atr.iloc[last],
        sma20.iloc[last],
        avg_volume.iloc[last],
        support.iloc[last]
    ]

    if any(pd.isna(x) for x in values):
        return None

    current_rsi = float(rsi.iloc[last])
    current_atr = float(atr.iloc[last])
    current_support = float(support.iloc[last])

    if current_atr <= 0:
        return None

    near_support = (
        price <= current_support + 1.8 * current_atr
    )

    rsi_recovery = (
        35 <= current_rsi <= 60
        and current_rsi > float(rsi.iloc[prev])
    )

    price_reversal = (
        price > float(close.iloc[prev])
        and price >= float(sma20.iloc[last])
    )

    volume_ok = (
        float(df["volume"].iloc[last])
        >= 0.8 * float(avg_volume.iloc[last])
    )

    if not all([
        near_support,
        rsi_recovery,
        price_reversal,
        volume_ok
    ]):
        return None

    return {
        "price": price,
        "support": current_support,
        "atr": current_atr,
        "rsi": current_rsi
    }


def create_signal(symbol, candidate, fundamentals):

    score, reasons = fundamental_score(fundamentals)

    if score < 3:
        return None

    price = candidate["price"]
    support = candidate["support"]
    atr = candidate["atr"]

    entry = price * 1.002

    stop = min(
        support - 0.5 * atr,
        entry - 1.5 * atr
    )

    risk_per_share = entry - stop

    if risk_per_share <= 0:
        return None

    risk_amount = CAPITAL * RISK_PERCENT

    quantity_risk = int(risk_amount // risk_per_share)
    quantity_capital = int(CAPITAL // entry)

    quantity = min(quantity_risk, quantity_capital)

    if quantity < 1:
        return None

    target1 = entry + 2 * risk_per_share
    target2 = entry + 3 * risk_per_share

    return {
        "symbol": symbol,
        "price": price,
        "entry": entry,
        "stop": stop,
        "target1": target1,
        "target2": target2,
        "quantity": quantity,
        "risk": quantity * risk_per_share,
        "score": score + 2,
        "reasons": reasons
    }


def main():

    if not API_TOKEN:
        log.error("EODHD token missing")
        return 2

    symbols = load_symbols()

    stats = Counter()
    signals = []

    log.info("Starting scan of %d stocks", len(symbols))

    for index, symbol in enumerate(symbols, 1):

        log.info("[%d/%d] %s", index, len(symbols), symbol)

        try:
            prices = get_prices(symbol)
            stats["price_ok"] += 1

        except requests.HTTPError as exc:

            if exc.response is not None and exc.response.status_code == 404:
                stats["price_404"] += 1
                log.warning("%s unavailable (404)", symbol)
                continue

            log.exception("Price API failure")
            return 1

        except Exception as exc:
            log.error("%s price failure: %s", symbol, exc)
            return 1

        candidate = technical_screen(prices)

        if candidate is None:
            stats["technical_reject"] += 1
            continue

        stats["technical_candidates"] += 1

        try:
            fundamentals = get_fundamentals(symbol)
            stats["fundamentals_ok"] += 1

        except requests.HTTPError as exc:

            if exc.response is not None and exc.response.status_code == 404:
                stats["fundamentals_404"] += 1
                continue

            log.exception("Fundamentals API failure")
            return 1

        except Exception as exc:
            log.error("%s fundamentals failure: %s", symbol, exc)
            return 1

        signal = create_signal(
            symbol,
            candidate,
            fundamentals
        )

        if signal:
            signals.append(signal)
            stats["signals"] += 1

    attempted = len(symbols)
    successful = stats["price_ok"]

    log.info("========== SCAN SUMMARY ==========")

    log.info("Stocks attempted: %d", attempted)
    log.info("Price history successful: %d", successful)
    log.info("Price 404: %d", stats["price_404"])
    log.info("Technical rejected: %d", stats["technical_reject"])
    log.info("Technical candidates: %d", stats["technical_candidates"])
    log.info("Fundamentals checked: %d", stats["fundamentals_ok"])
    log.info("Fundamentals unavailable: %d", stats["fundamentals_404"])
    log.info("Signals: %d", len(signals))

    coverage = successful / attempted if attempted else 0

    if coverage < MIN_COVERAGE:

        message = (
            f"SCANNER DATA WARNING: only {successful}/{attempted} "
            "stocks returned usable price history. Scan incomplete."
        )

        log.error(message)

        try:
            telegram(message)
        except Exception:
            log.exception("Telegram failed")

        return 1

    signals.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    if signals:

        message = "INDIAN SWING SCANNER RESULTS\n\n"

        for s in signals[:10]:

            message += (
                f"{s['symbol']}\n"
                f"Close: Rs.{s['price']:.2f}\n"
                f"Entry: Rs.{s['entry']:.2f}\n"
                f"Stop: Rs.{s['stop']:.2f}\n"
                f"Target 1: Rs.{s['target1']:.2f}\n"
                f"Target 2: Rs.{s['target2']:.2f}\n"
                f"Quantity: {s['quantity']}\n"
                f"Risk: Rs.{s['risk']:.2f}\n"
                f"Score: {s['score']}\n\n"
            )

    else:

        message = (
            f"No qualifying setups today.\n"
            f"Data coverage: {successful}/{attempted}"
        )

    print(message)

    try:
        telegram(message[:3900])
    except Exception:
        log.exception("Telegram delivery failed")

    log.info("Scan completed successfully")

    return 0


if __name__ == "__main__":
    sys.exit(main())
  
