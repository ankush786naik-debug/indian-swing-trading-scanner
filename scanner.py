#!/usr/bin/env python3
"""
Indian Swing Trading Scanner
----------------------------
Scans up to 500 NSE stocks using EODHD daily prices and fundamentals.

Required environment variables:
  EODHD_API_TOKEN       EODHD API token
Optional:
  CAPITAL                Trading capital in INR (default: 100000)
  MIN_STOCK_PRICE        Minimum stock price (default: 200)
  MAX_STOCKS             Maximum symbols to scan (default: 50)
  RISK_PER_TRADE         Fraction of capital risked per trade (default: 0.01)
  TELEGRAM_BOT_TOKEN     Telegram bot token (optional)
  TELEGRAM_CHAT_ID       Telegram chat/channel ID (optional)
  SYMBOLS_FILE           Path to symbols file (default: symbols.txt)

symbols.txt should contain one EODHD symbol per line, e.g.:
  RELIANCE.NSE
  TCS.NSE
  HDFCBANK.NSE

This is a screening/education tool, not investment advice. Verify every
signal and price independently before placing an order.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://eodhd.com/api"
API_TOKEN = os.getenv("EODHD_API_TOKEN", "").strip()
CAPITAL = float(os.getenv("CAPITAL", "100000"))
MIN_STOCK_PRICE = float(os.getenv("MIN_STOCK_PRICE", "200"))
MAX_STOCKS = int(os.getenv("MAX_STOCKS", "500"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.01"))
SYMBOLS_FILE = os.getenv("SYMBOLS_FILE", "symbols.txt")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("swing-scanner")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "IndianSwingScanner/1.0"})


@dataclass
class Signal:
    symbol: str
    price: float
    entry: float
    stop_loss: float
    target_1: float
    target_2: float
    quantity: int
    risk_amount: float
    reward_risk: float
    score: int
    reason: str


def api_get(path: str, params: dict[str, Any] | None = None) -> Any:
    if not API_TOKEN:
        raise RuntimeError("EODHD_API_TOKEN is missing. Add it to GitHub Secrets/.env.")
    query = dict(params or {})
    query["api_token"] = API_TOKEN
    query["fmt"] = "json"
    response = SESSION.get(f"{BASE_URL}/{path.lstrip('/')}", params=query, timeout=30)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(str(data["error"]))
    return data


def load_symbols() -> list[str]:
    path = SYMBOLS_FILE
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found. Create it with one EODHD NSE ticker per line, "
            "for example RELIANCE.NSE."
        )
    symbols: list[str] = []
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle:
            value = raw.strip().upper()
            if value and not value.startswith("#") and value not in symbols:
                symbols.append(value)
    if not symbols:
        raise ValueError(f"No symbols found in {path}.")
    return symbols[:MAX_STOCKS]


def get_history(symbol: str) -> pd.DataFrame:
    end = date.today()
    start = end - timedelta(days=420)
    rows = api_get(
        f"eod/{symbol}",
        {"from": start.isoformat(), "to": end.isoformat(), "period": "d"},
    )
    if not isinstance(rows, list) or len(rows) < 80:
        raise ValueError(f"Insufficient daily price history for {symbol}.")
    frame = pd.DataFrame(rows)
    required = {"date", "open", "high", "low", "close", "volume"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Unexpected price response for {symbol}: missing OHLCV fields.")
    frame["date"] = pd.to_datetime(frame["date"])
    for col in ("open", "high", "low", "close", "volume"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["close", "high", "low", "volume"])
    return frame.sort_values("date").reset_index(drop=True)


def get_fundamentals(symbol: str) -> dict[str, Any]:
    data = api_get(f"fundamentals/{symbol}")
    if not isinstance(data, dict):
        return {}
    return data


def as_float(value: Any) -> float | None:
    try:
        result = float(value)
        return result if np.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def first_number(mapping: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = as_float(mapping.get(key))
        if value is not None:
            return value
    return None


def fundamental_score(data: dict[str, Any]) -> tuple[int, list[str]]:
    highlights = data.get("Highlights") or {}
    valuation = data.get("Valuation") or {}
    score = 0
    reasons: list[str] = []

    roe = first_number(highlights, "ReturnOnEquityTTM", "ReturnOnEquity")
    margin = first_number(highlights, "ProfitMargin")
    revenue_growth = first_number(highlights, "RevenueGrowth")
    earnings_growth = first_number(highlights, "EarningsGrowth")
    pe = first_number(valuation, "TrailingPE", "ForwardPE")
    pb = first_number(valuation, "PriceBookMRQ")

    if roe is not None and roe >= 15:
        score += 2
        reasons.append(f"ROE {roe:.1f}%")
    if margin is not None and margin >= 10:
        score += 1
        reasons.append(f"profit margin {margin:.1f}%")
    if revenue_growth is not None and revenue_growth > 0:
        score += 1
        reasons.append("positive revenue growth")
    if earnings_growth is not None and earnings_growth > 0:
        score += 1
        reasons.append("positive earnings growth")
    if pe is not None and 0 < pe <= 35:
        score += 1
        reasons.append(f"P/E {pe:.1f}")
    if pb is not None and 0 < pb <= 6:
        score += 1
        reasons.append(f"P/B {pb:.1f}")

    # Missing fundamentals are not treated as passing.
    return score, reasons


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    close = out["close"]
    out["sma20"] = close.rolling(20).mean()
    out["sma50"] = close.rolling(50).mean()
    out["sma200"] = close.rolling(200).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    out["rsi"] = 100 - (100 / (1 + rs))
    previous_close = close.shift(1)
    tr = pd.concat(
        [
            out["high"] - out["low"],
            (out["high"] - previous_close).abs(),
            (out["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr"] = tr.rolling(14).mean()
    out["avg_volume20"] = out["volume"].rolling(20).mean()
    out["support20"] = out["low"].rolling(20).min()
    out["resistance20"] = out["high"].rolling(20).max()
    return out


def evaluate(
    symbol: str, prices: pd.DataFrame, fundamentals: dict[str, Any]
) -> Signal | None:
    df = add_indicators(prices)
    last = df.iloc[-1]
    prev = df.iloc[-2]

    price = float(last["close"])
    if not np.isfinite(price) or price < MIN_STOCK_PRICE:
        return None

    values = [last.get("rsi"), last.get("atr"), last.get("sma20"),
              last.get("sma50"), last.get("support20"), last.get("avg_volume20")]
    if any(pd.isna(v) for v in values):
        return None

    support = float(last["support20"])
    atr = float(last["atr"])
    rsi = float(last["rsi"])
    avg_volume = float(last["avg_volume20"])
    if atr <= 0 or avg_volume <= 0:
        return None

    # Reversal setup: price is near its 20-day support, RSI is recovering,
    # and today's close is above yesterday's close and the 20-day average.
    near_support = price <= support + (1.8 * atr)
    rsi_recovering = 35 <= rsi <= 60 and float(prev["rsi"]) < rsi
    price_reversal = price > float(prev["close"]) and price >= float(last["sma20"])
    volume_ok = float(last["volume"]) >= 0.8 * avg_volume
    if not (near_support and rsi_recovering and price_reversal and volume_ok):
        return None

    f_score, f_reasons = fundamental_score(fundamentals)
    if f_score < 3:
        return None

    entry = price * 1.002
    stop = min(support - 0.5 * atr, entry - 1.5 * atr)
    risk_per_share = entry - stop
    if risk_per_share <= 0:
        return None

    risk_amount = CAPITAL * RISK_PER_TRADE
    qty_by_risk = int(risk_amount // risk_per_share)
    qty_by_capital = int(CAPITAL // entry)
    quantity = max(0, min(qty_by_risk, qty_by_capital))
    if quantity < 1:
        return None

    target_1 = entry + (2 * risk_per_share)
    target_2 = entry + (3 * risk_per_share)
    reward_risk = (target_1 - entry) / risk_per_share

    score = f_score + 2  # technical setup passed
    reason = "; ".join(f_reasons + [
        f"near support ({support:.2f})",
        f"RSI recovering ({rsi:.1f})",
        "reversal/volume conditions passed",
    ])
    return Signal(
        symbol=symbol, price=price, entry=entry, stop_loss=stop,
        target_1=target_1, target_2=target_2, quantity=quantity,
        risk_amount=quantity * risk_per_share, reward_risk=reward_risk,
        score=score, reason=reason,
    )


def send_telegram(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.info("Telegram not configured; skipping alert.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    response = SESSION.post(
        url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=20
    )
    response.raise_for_status()


def format_signal(signal: Signal) -> str:
    return (
        f"📈 SWING SETUP: {signal.symbol}\n"
        f"Last close: ₹{signal.price:.2f}\n"
        f"Entry: ₹{signal.entry:.2f}\n"
        f"Stop loss: ₹{signal.stop_loss:.2f}\n"
        f"Target 1: ₹{signal.target_1:.2f}\n"
        f"Target 2: ₹{signal.target_2:.2f}\n"
        f"Quantity: {signal.quantity} shares\n"
        f"Estimated risk: ₹{signal.risk_amount:.0f}\n"
        f"Reward/risk to T1: {signal.reward_risk:.1f}:1\n"
        f"Setup score: {signal.score}\n"
        f"Why: {signal.reason}\n"
        "Research alert only — verify prices and liquidity before trading."
    )


def main() -> int:
    if not API_TOKEN:
        log.error("EODHD_API_TOKEN is not configured.")
        return 2
    try:
        symbols = load_symbols()
    except Exception as exc:
        log.error("%s", exc)
        return 2

    log.info("Starting scan for %d symbols; capital ₹%.0f", len(symbols), CAPITAL)
    signals: list[Signal] = []
    failures = 0

    for index, symbol in enumerate(symbols, start=1):
        try:
            log.info("[%d/%d] Scanning %s", index, len(symbols), symbol)
            prices = get_history(symbol)
            fundamentals = get_fundamentals(symbol)
            signal = evaluate(symbol, prices, fundamentals)
            if signal:
                signals.append(signal)
                log.info("Signal found: %s", symbol)
        except requests.HTTPError as exc:
            failures += 1
            log.warning("%s: API HTTP error: %s", symbol, exc)
        except Exception as exc:
            failures += 1
            log.warning("%s: skipped: %s", symbol, exc)

    signals.sort(key=lambda item: (item.score, item.reward_risk), reverse=True)
    if signals:
        message = "🇮🇳 INDIAN SWING SCANNER — DAILY RESULTS\n\n"
        message += "\n\n".join(format_signal(item) for item in signals[:10])
        print(message)
        try:
            send_telegram(message[:3900])
        except Exception as exc:
            log.error("Telegram alert failed: %s", exc)
    else:
        message = "Indian Swing Scanner: no qualifying setups found today."
        print(message)
        try:
            send_telegram(message)
        except Exception as exc:
            log.error("Telegram alert failed: %s", exc)

    log.info("Scan complete. Signals: %d | Failed/skipped: %d", len(signals), failures)
    return 0


if __name__ == "__main__":
    sys.exit(main())
