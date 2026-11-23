# Indian NSE Top-5 Swing Research Scanner

Daily, read-only stock research scanner using **Upstox** market data, company fundamentals and instrument news. It does not place orders and does not promise profits.

## What it does
1. Downloads Upstox's daily NSE instrument master and dynamically includes all NSE_EQ / EQ stocks available in the master. No static Nifty 500 or 1,000-symbol list and no stock-price boundary.
2. Uses batched Upstox full-market quotes to screen the complete universe by valid price/volume and a configurable minimum daily turnover (default ₹3 crore).
3. Fetches daily candles for the **350 most liquid stocks that day** (dynamic candidates, not a hard-coded membership list) to stay within Upstox's published API request limits.
4. Ranks technical swing setups (trend, pullback/support, RSI, MACD, volume, risk and reward).
5. Researches the leading 25 technical candidates with Upstox company ratios, income statement, cash flow, balance sheet and Upstox news from the previous 7 days.
6. Sends a CSV containing up to 5 qualified stocks to Telegram and saves it as:
   - `data/top5_swing_stocks.csv` (latest)
   - `data/top5_swing_stocks_YYYY-MM-DD.csv` (dated copy)

If fewer than five stocks meet the minimum score, the CSV contains only those qualified stocks; if none qualify, it contains headers and no stock rows. No forced picks.

## GitHub Actions secrets
Add these in **Settings → Secrets and variables → Actions**:
- `UPSTOX_ANALYTICS_TOKEN` — Upstox Analytics Token. It is read-only and intended for market-data access. Add it separately to this repository even if it exists in another repo.
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Use the Analytics Token rather than a standard access token if available; standard OAuth access tokens expire daily. Never commit tokens into files.

## Schedule
Weekdays at 4:45 PM IST, after the NSE cash session. Manual trigger is available under Actions → Daily NSE Top-5 Swing Research → Run workflow.

## Research scoring
Combined score: 45% technical setup, 40% fundamentals, 15% recent news. Negative news can disqualify a candidate. Fundamentals include ROCE, ROE, revenue/profit growth, operating cash flow, valuation relative to sector and liabilities/assets when the API provides sufficient data. News comes from Upstox's instrument news endpoint (articles from the previous 7 days).

## Important limits and validation
Upstox full-market quotes support batches up to 500 instruments; news supports up to 30 instrument keys per request. Standard API rate limits are 500 requests/minute and 2,000 per 30 minutes. The scanner therefore screens all NSE equity quotes but deep-candle analyses a dynamic liquid shortlist, then researches a smaller group. It cannot request historical candles for every several-thousand NSE equity daily within those quotas.

The first live run is required to validate your token's access to quotes, candles, fundamentals and news and the actual response fields. Missing fundamentals/news are not treated as positive. Review the CSV and verify live price before entry; stops/targets are modelled levels, not guarantees.
