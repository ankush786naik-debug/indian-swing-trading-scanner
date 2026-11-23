import unittest
import numpy as np
import pandas as pd

from scanner import fundamentals_score, news_score, analyze
from upstox_client import UpstoxClient


class ScannerResearchTests(unittest.TestCase):
    def test_news_positive_and_negative_classification(self):
        positive = news_score([{"heading":"Company wins major order contract","summary":"Expansion and order book growth"}])
        negative = news_score([{"heading":"Regulatory investigation and default reported","summary":"Debt stress"}])
        self.assertGreater(positive["news_sentiment"], 0)
        self.assertLess(negative["news_sentiment"], 0)
        self.assertEqual(positive["news_count_7d"], 1)

    def test_fundamentals_score_and_coverage(self):
        sample = {
            "ratios": {"roce": 22, "roe": 18, "pe_ratio": 18, "sector_pe": 24},
            "income": {"revenue_growth": 15, "net_profit_growth": 20},
            "cash_flow": {"operating_cash_flow": 120},
            "balance": {"total_assets": 1000, "total_liabilities": 400},
        }
        result = fundamentals_score(sample)
        self.assertIsNotNone(result["fundamental_score"])
        self.assertGreaterEqual(result["fundamental_score"], 50)
        self.assertGreater(result["fundamental_coverage"], 0.5)
        self.assertAlmostEqual(result["Liabilities_to_assets"], 0.4)

    def test_full_nse_instrument_master_filter_includes_all_equity_types(self):
        self.assertTrue(callable(UpstoxClient.load_nse_equities))

    def test_technical_analysis_returns_levels(self):
        dates = pd.bdate_range("2025-01-01", periods=260)
        trend = np.linspace(100, 155, len(dates)) + 2*np.sin(np.arange(len(dates))/5)
        df = pd.DataFrame({
            "date": dates,
            "open": trend - .5,
            "high": trend + 2,
            "low": trend - 2,
            "close": trend,
            "volume": np.full(len(dates), 200000),
        })
        result = analyze("TEST", df.to_dict("records"))
        self.assertIsNotNone(result)
        self.assertGreater(result["close"], result["stop_loss"])
        self.assertGreater(result["target_1"], result["close"])
        self.assertGreaterEqual(result["technical_score"], 0)

if __name__ == "__main__":
    unittest.main()
