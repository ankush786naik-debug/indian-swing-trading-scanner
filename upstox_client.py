"""Upstox market-data client for the NSE swing scanner."""
import gzip
import json
import os
import time
from urllib.parse import quote

import requests

BASE_URL = "https://api.upstox.com"
NSE_MASTER_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"


class UpstoxAPIError(RuntimeError):
    pass


class UpstoxClient:
    def __init__(self, token=None, timeout=25):
        self.token = (token or os.getenv("UPSTOX_ANALYTICS_TOKEN") or
                      os.getenv("UPSTOX_ACCESS_TOKEN") or "").strip()
        if not self.token:
            raise UpstoxAPIError(
                "Missing UPSTOX_ANALYTICS_TOKEN GitHub secret. Use your Upstox Analytics Token."
            )
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "IndianSwingScanner/2.0",
        })
        self.last_request = 0.0

    def get(self, path, params=None, attempts=4):
        # Respect the published 500/min and 2,000/30-minute standard API limits.
        delay = max(0.13, 0.13 - (time.monotonic() - self.last_request))
        if delay > 0:
            time.sleep(delay)
        url = f"{BASE_URL}{path}"
        for attempt in range(attempts):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                self.last_request = time.monotonic()
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt + 1 < attempts:
                        time.sleep(min(2 ** attempt, 12))
                        continue
                response.raise_for_status()
                payload = response.json()
                if payload.get("status") == "error":
                    raise UpstoxAPIError(str(payload))
                return payload.get("data", payload)
            except requests.RequestException as exc:
                if attempt + 1 >= attempts:
                    raise UpstoxAPIError(f"Upstox request failed: {exc}") from exc
                time.sleep(min(2 ** attempt, 12))
        raise UpstoxAPIError(f"Upstox request failed after retries: {path}")

    @staticmethod
    def load_nse_equities():
        response = requests.get(NSE_MASTER_URL, timeout=45)
        response.raise_for_status()
        raw = gzip.decompress(response.content)
        items = json.loads(raw.decode("utf-8"))
        universe = []
        seen = set()
        for row in items:
            if row.get("segment") != "NSE_EQ" or row.get("instrument_type") != "EQ":
                continue
            if row.get("security_type") not in (None, "", "NORMAL"):
                continue
            key = row.get("instrument_key")
            symbol = row.get("trading_symbol")
            if not key or not symbol or key in seen:
                continue
            seen.add(key)
            universe.append({
                "instrument_key": key,
                "symbol": symbol,
                "name": row.get("name") or row.get("short_name") or symbol,
                "isin": row.get("isin") or "",
            })
        if not universe:
            raise UpstoxAPIError("Upstox NSE instrument master returned zero NSE_EQ instruments.")
        return sorted(universe, key=lambda x: x["symbol"])

    def quotes(self, instrument_keys):
        result = {}
        for start in range(0, len(instrument_keys), 500):
            batch = instrument_keys[start:start + 500]
            data = self.get("/v2/market-quote/quotes", params={
                "instrument_key": ",".join(batch)
            })
            if isinstance(data, dict):
                result.update(data)
        return result

    def daily_candles(self, instrument_key, from_date, to_date):
        encoded = quote(instrument_key, safe="")
        data = self.get(
            f"/v3/historical-candle/{encoded}/days/1/{to_date}/{from_date}"
        )
        candles = data.get("candles", []) if isinstance(data, dict) else []
        rows = []
        for candle in candles:
            if len(candle) < 6:
                continue
            rows.append({
                "date": candle[0],
                "open": candle[1],
                "high": candle[2],
                "low": candle[3],
                "close": candle[4],
                "volume": candle[5],
            })
        return rows

    def fundamentals(self, isin):
        if not isin:
            return {}
        endpoints = {
            "ratios": f"/v2/fundamentals/{isin}/key-ratios",
            "income": f"/v2/fundamentals/{isin}/income-statement",
            "cash_flow": f"/v2/fundamentals/{isin}/cash-flow",
            "balance": f"/v2/fundamentals/{isin}/balance-sheet",
            "profile": f"/v2/fundamentals/{isin}/profile",
        }
        result = {}
        for key, path in endpoints.items():
            try:
                result[key] = self.get(path)
            except UpstoxAPIError as exc:
                result[key] = {"_error": str(exc)}
        return result

    def news(self, instrument_keys):
        output = {}
        for start in range(0, len(instrument_keys), 30):
            batch = instrument_keys[start:start + 30]
            data = self.get("/v2/news", params={
                "category": "instrument_keys",
                "instrument_keys": ",".join(batch),
                "page_number": 1,
                "page_size": 100,
            })
            if isinstance(data, dict):
                output.update(data)
        return output

    def close(self):
        self.session.close()
