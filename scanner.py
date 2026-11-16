
"""
NSE Positional Trading Scanner
Holding period: approximately 2-3 months.

Signals:
BUY ENTRY
HOLD
EXIT
SHORT WATCH

Data: TejHQ historical OHLCV
"""

import os
import time
import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd

from Tej_client import TejClient, TejAPIError
from exporters import export_csv, export_json


# ---------------- CONFIGURATION ----------------

SYMBOL_FILE = "symbols.txt"
OUTPUT_DIR = "data"

EXCHANGE = "nse"

HISTORY_DAYS = 450

MIN_HISTORY = 220

REQUEST_DELAY = 0.15

RSI_PERIOD = 14
ATR_PERIOD = 14

SHORT_EMA = 20
MEDIUM_EMA = 50
LONG_EMA = 200

VOLUME_PERIOD = 20

# ATR-based trade planning
STOP_ATR = 2.5
TARGET_ONE_R = 2.0
TARGET_TWO_R = 3.0

# Technical filters
MIN_ADX = 18
MIN_BUY_SCORE = 70
MIN_SHORT_SCORE = 70

os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


# ---------------- SYMBOL LOADER ----------------


def load_symbols():
    if not os.path.exists(SYMBOL_FILE):
        raise FileNotFoundError("symbols.txt not found.")

    symbols = []

    with open(SYMBOL_FILE, "r", encoding="utf-8") as file:
        for line in file:
            symbol = line.strip().upper()

            if not symbol or symbol.startswith("#"):
                continue

            if symbol in ("SYMBOL", "SYMBOLS", "TICKER"):
                continue

            # TejHQ receives exchange separately as "nse".
            # Remove exchange suffixes from the symbol.
            for suffix in (".NSE", ".NS"):
                if symbol.endswith(suffix):
                    symbol = symbol[:-len(suffix)]
                    break

            if symbol:
                symbols.append(symbol)

    return sorted(set(symbols))
    


# ---------------- DATA NORMALIZATION ----------------

def normalize_data(raw):

    if isinstance(raw, dict):

        for key in ("data", "historical", "results"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break

    if not isinstance(raw, list) or not raw:
        return None

    df = pd.DataFrame(raw)

    df.columns = [
        str(column).lower().strip()
        for column in df.columns
    ]

    aliases = {
        "datetime": "date",
        "timestamp": "date",
        "adj_close": "adjusted_close",
    }

    df = df.rename(columns=aliases)

    required = [
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume"
    ]

    if not all(column in df.columns for column in required):
        return None

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce",
        utc=True
    )

    # Convert UTC dates to date-only values.
    df["date"] = df["date"].dt.tz_convert(None)

    for column in required[1:]:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df = df.dropna(subset=required)

    df = df.sort_values("date")
    df = df.drop_duplicates(subset="date")

    return df.reset_index(drop=True)


# ---------------- TECHNICAL INDICATORS ----------------

def calculate_indicators(df):

    df = df.copy()

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # EMA
    df["ema20"] = close.ewm(
        span=20,
        adjust=False
    ).mean()

    df["ema50"] = close.ewm(
        span=50,
        adjust=False
    ).mean()

    df["ema200"] = close.ewm(
        span=200,
        adjust=False
    ).mean()

    # RSI
    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / RSI_PERIOD,
        adjust=False,
        min_periods=RSI_PERIOD
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / RSI_PERIOD,
        adjust=False,
        min_periods=RSI_PERIOD
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    df["rsi"] = 100 - (100 / (1 + rs))

    df["rsi"] = df["rsi"].fillna(100)

    # MACD
    ema12 = close.ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = close.ewm(
        span=26,
        adjust=False
    ).mean()

    df["macd"] = ema12 - ema26

    df["macd_signal"] = df["macd"].ewm(
        span=9,
        adjust=False
    ).mean()

    df["macd_hist"] = (
        df["macd"] - df["macd_signal"]
    )

    # ATR
    previous_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs()
        ],
        axis=1
    ).max(axis=1)

    df["atr"] = tr.ewm(
        alpha=1 / ATR_PERIOD,
        adjust=False,
        min_periods=ATR_PERIOD
    ).mean()

    # ADX
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where(
            (up_move > down_move) & (up_move > 0),
            up_move,
            0
        ),
        index=df.index
    )

    minus_dm = pd.Series(
        np.where(
            (down_move > up_move) & (down_move > 0),
            down_move,
            0
        ),
        index=df.index
    )

    atr_safe = df["atr"].replace(0, np.nan)

    plus_di = 100 * (
        plus_dm.ewm(
            alpha=1 / ATR_PERIOD,
            adjust=False
        ).mean() / atr_safe
    )

    minus_di = 100 * (
        minus_dm.ewm(
            alpha=1 / ATR_PERIOD,
            adjust=False
        ).mean() / atr_safe
    )

    dx = (
        100 * (plus_di - minus_di).abs()
        / (plus_di + minus_di).replace(0, np.nan)
    )

    df["adx"] = dx.ewm(
        alpha=1 / ATR_PERIOD,
        adjust=False
    ).mean()

    df["plus_di"] = plus_di
    df["minus_di"] = minus_di

    # Volume confirmation
    df["volume_avg20"] = volume.rolling(
        VOLUME_PERIOD
    ).mean()

    df["volume_ratio"] = (
        volume / df["volume_avg20"].replace(0, np.nan)
    )

    # Price structure
    df["resistance20"] = high.shift(1).rolling(20).max()
    df["support20"] = low.shift(1).rolling(20).min()

    return df


# ---------------- WEEKLY TREND ----------------

def calculate_weekly_trend(df):

    weekly = (
        df.set_index("date")
        .resample("W-FRI")
        .agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum"
        })
        .dropna()
        .reset_index()
    )

    if len(weekly) < 40:
        return "INSUFFICIENT HISTORY"

    weekly["ema20"] = weekly["close"].ewm(
        span=20,
        adjust=False
    ).mean()

    weekly["ema40"] = weekly["close"].ewm(
        span=40,
        adjust=False
    ).mean()

    last = weekly.iloc[-1]

    if (
        last["close"] > last["ema20"]
        and last["ema20"] > last["ema40"]
    ):
        return "BULLISH"

    if (
        last["close"] < last["ema20"]
        and last["ema20"] < last["ema40"]
    ):
        return "BEARISH"

    return "SIDEWAYS"


# ---------------- SIGNAL ENGINE ----------------

def analyze_stock(symbol, df):

    if df is None or len(df) < MIN_HISTORY:
        return None

    df = calculate_indicators(df)

    current = df.iloc[-1]
    previous = df.iloc[-2]

    price = float(current["close"])
    atr = float(current["atr"])

    if not np.isfinite(atr) or atr <= 0:
        return None

    if not np.isfinite(current["ema200"]):
        return None

    weekly_trend = calculate_weekly_trend(df)

    bullish_score = 0
    bearish_score = 0
    reasons = []

    # -------- BULLISH CONDITIONS --------

    if price > current["ema200"]:
        bullish_score += 20
        reasons.append("Price above EMA200")

    if current["ema20"] > current["ema50"]:
        bullish_score += 15
        reasons.append("EMA20 above EMA50")

    if current["ema50"] > current["ema200"]:
        bullish_score += 15
        reasons.append("EMA50 above EMA200")

    if 50 <= current["rsi"] <= 70:
        bullish_score += 10
        reasons.append("Positive RSI momentum")

    if current["macd"] > current["macd_signal"]:
        bullish_score += 10
        reasons.append("MACD bullish")

    if current["adx"] >= MIN_ADX:
        if current["plus_di"] > current["minus_di"]:
            bullish_score += 10
            reasons.append("Strong positive trend")

    if current["volume_ratio"] >= 1.3:
        bullish_score += 10
        reasons.append("Volume confirmation")

    if weekly_trend == "BULLISH":
        bullish_score += 10
        reasons.append("Weekly trend bullish")

    # -------- BEARISH CONDITIONS --------

    if price < current["ema200"]:
        bearish_score += 20

    if current["ema20"] < current["ema50"]:
        bearish_score += 15

    if current["ema50"] < current["ema200"]:
        bearish_score += 15

    if current["rsi"] < 45:
        bearish_score += 10

    if current["macd"] < current["macd_signal"]:
        bearish_score += 10

    if current["adx"] >= MIN_ADX:
        if current["minus_di"] > current["plus_di"]:
            bearish_score += 10

    if current["volume_ratio"] >= 1.3:
        bearish_score += 10

    if weekly_trend == "BEARISH":
        bearish_score += 10

    # -------- ENTRY / EXIT LEVELS --------

    long_stop = price - STOP_ATR * atr
    long_risk = price - long_stop

    long_target1 = price + TARGET_ONE_R * long_risk
    long_target2 = price + TARGET_TWO_R * long_risk

    short_stop = price + STOP_ATR * atr
    short_risk = short_stop - price

    short_target1 = price - TARGET_ONE_R * short_risk
    short_target2 = price - TARGET_TWO_R * short_risk

    resistance = float(current["resistance20"])
    support = float(current["support20"])

    bullish_breakout = (
        price > resistance
        and current["volume_ratio"] >= 1.3
    )

    bearish_breakdown = (
        price < support
        and current["volume_ratio"] >= 1.3
    )

    signal = "WATCH"
    entry_price = None
    stop_loss = None
    target1 = None
    target2 = None

    # BUY
    if (
        bullish_score >= MIN_BUY_SCORE
        and weekly_trend == "BULLISH"
    ):

        signal = "BUY ENTRY"
        entry_price = price
        stop_loss = long_stop
        target1 = long_target1
        target2 = long_target2

        if bullish_breakout:
            reasons.append("20-day resistance breakout")

    # EXIT for long positions
    elif (
        price < current["ema50"]
        and current["macd"] < current["macd_signal"]
        and weekly_trend != "BULLISH"
    ):

        signal = "EXIT LONG"
        reasons.append("Trend deterioration")

    # SHORT WATCH
    elif (
        bearish_score >= MIN_SHORT_SCORE
        and weekly_trend == "BEARISH"
        and bearish_breakdown
    ):

        signal = "SHORT WATCH"
        entry_price = price
        stop_loss = short_stop
        target1 = short_target1
        target2 = short_target2

        reasons.append("20-day support breakdown")

    # HOLD
    elif (
        price > current["ema50"]
        and weekly_trend == "BULLISH"
        and current["macd"] > current["macd_signal"]
    ):

        signal = "HOLD"
        reasons.append("Existing bullish trend intact")

    # -------- OUTPUT --------

    return {
        "symbol": symbol,
        "date": str(current["date"].date()),
        "signal": signal,
        "price": round(price, 2),
        "entry_price": (
            round(entry_price, 2)
            if entry_price is not None else None
        ),
        "stop_loss": (
            round(stop_loss, 2)
            if stop_loss is not None else None
        ),
        "target_1": (
            round(target1, 2)
            if target1 is not None else None
        ),
        "target_2": (
            round(target2, 2)
            if target2 is not None else None
        ),
        "rsi": round(float(current["rsi"]), 2),
        "adx": round(float(current["adx"]), 2),
        "atr": round(atr, 2),
        "volume_ratio": (
            round(float(current["volume_ratio"]), 2)
            if np.isfinite(current["volume_ratio"])
            else None
        ),
        "bullish_score": bullish_score,
        "bearish_score": bearish_score,
        "weekly_trend": weekly_trend,
        "reasons": "; ".join(reasons),
        "holding_period": "2-3 months"
    }


# ---------------- MAIN SCANNER ----------------

def run_scanner():

    symbols = load_symbols()

    logging.info(
        "Starting NSE scanner for %s symbols",
        len(symbols)
    )

    client = TejClient()

    results = []
    failures = []

    end_date = date.today()

    start_date = end_date - timedelta(
        days=HISTORY_DAYS
    )

    try:

        for index, symbol in enumerate(symbols, start=1):

            try:

                logging.info(
                    "[%s/%s] Scanning %s",
                    index,
                    len(symbols),
                    symbol
                )

                raw = client.get_ohlcv(
                    symbol,
                    EXCHANGE,
                    start_date.isoformat(),
                    end_date.isoformat()
                )

                df = normalize_data(raw)

                if df is None:
                    failures.append({
                        "symbol": symbol,
                        "error": "No valid OHLCV data"
                    })
                    continue

                result = analyze_stock(symbol, df)

                if result:
                    results.append(result)
                else:
                    failures.append({
                        "symbol": symbol,
                        "error": "Insufficient history or indicators"
                    })

            except Exception as error:

                logging.warning(
                    "%s failed: %s",
                    symbol,
                    error
                )

                failures.append({
                    "symbol": symbol,
                    "error": str(error)
                })

            time.sleep(REQUEST_DELAY)

    finally:
        client.close()

    if not results:
        logging.warning("No valid scanner results.")
        return

    result_df = pd.DataFrame(results)

    result_df = result_df.sort_values(
        by=["bullish_score", "bearish_score"],
        ascending=False
    )

    # Save all results
    export_csv(
        result_df.to_dict("records"),
        "nse_scanner_all.csv"
    )

    export_json(
        result_df.to_dict("records"),
        "nse_scanner_all.json"
    )

    # Save BUY signals
    buys = result_df[
        result_df["signal"] == "BUY ENTRY"
    ]

    export_csv(
        buys.to_dict("records"),
        "nse_buy_signals.csv"
    )

    # Save EXIT signals
    exits = result_df[
        result_df["signal"] == "EXIT LONG"
    ]

    export_csv(
        exits.to_dict("records"),
        "nse_exit_signals.csv"
    )

    # Save short watchlist
    shorts = result_df[
        result_df["signal"] == "SHORT WATCH"
    ]

    export_csv(
        shorts.to_dict("records"),
        "nse_short_watch.csv"
    )

    # Save HOLD signals
    holds = result_df[
        result_df["signal"] == "HOLD"
    ]

    export_csv(
        holds.to_dict("records"),
        "nse_hold_signals.csv"
    )

    export_json(
        failures,
        "nse_scan_failures.json"
    )

    print("\n========== NSE SCANNER REPORT ==========")

    print(f"Symbols loaded: {len(symbols)}")
    print(f"Successful analysis: {len(results)}")
    print(f"Failed symbols: {len(failures)}")

    print(f"BUY ENTRY: {len(buys)}")
    print(f"HOLD: {len(holds)}")
    print(f"EXIT LONG: {len(exits)}")
    print(f"SHORT WATCH: {len(shorts)}")

    print("\nTOP BUY CANDIDATES")

    print(
        buys[
            [
                "symbol",
                "price",
                "entry_price",
                "stop_loss",
                "target_1",
                "target_2",
                "bullish_score"
            ]
        ].head(20).to_string(index=False)
    )

    print("\nFiles saved in data/ directory.")


if __name__ == "__main__":
    run_scanner()
    
