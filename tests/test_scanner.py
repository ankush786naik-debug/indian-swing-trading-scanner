import unittest
from unittest.mock import Mock

from Tej_client import TejClient
from scanner import clean_symbol, normalize_data


class TejClientTests(unittest.TestCase):
    def test_get_ohlcv_removes_exchange_suffix(self):
        client = TejClient()
        client.request = Mock(return_value={"data": [{"date": "2026-11-20"}]})

        result = client.get_ohlcv(
            "RELIANCE.NSE",
            exchange="nse",
            from_date="2025-11-20",
            to_date="2026-11-20",
        )

        client.request.assert_called_once_with(
            "/v1/ohlcv/nse/RELIANCE",
            {"from": "2025-11-20", "to": "2026-11-20"},
        )
        self.assertEqual(result, [{"date": "2026-11-20"}])
        client.close()

    def test_clean_symbol(self):
        self.assertEqual(clean_symbol("NSE:RELIANCE.NSE"), "RELIANCE")
        self.assertEqual(clean_symbol("M&M.NSE"), "M&M")
        self.assertEqual(clean_symbol("BAJAJ-AUTO.NSE"), "BAJAJ-AUTO")

    def test_normalize_tejhq_envelope(self):
        raw = {
            "data": [{
                "date": "2026-11-20",
                "open": 100,
                "high": 105,
                "low": 98,
                "close": 103,
                "volume": 100000,
            }],
            "meta": {"symbol": "TEST"},
        }
        frame = normalize_data(raw)
        self.assertIsNotNone(frame)
        self.assertEqual(len(frame), 1)
        self.assertEqual(float(frame.iloc[0]["close"]), 103.0)


if __name__ == "__main__":
    unittest.main()
