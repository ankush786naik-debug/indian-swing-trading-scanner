
# NSE Market Data API

Python integration for TejHQ Indian stock market data.

## Features

- NSE historical OHLCV
- NSE full market snapshots
- Corporate actions
- Adjusted historical prices
- Delivery data
- NSE symbol history
- JSON and CSV exports

## Installation

Python 3.10 or later recommended.

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it:

Windows:

```bash
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env`.

Add your TejHQ API key:

```env
TEJ_API_BASE_URL=https://api.tejhq.dev
TEJ_API_KEY=YOUR_TEJHQ_KEY
DEFAULT_EXCHANGE=nse
REQUEST_TIMEOUT=30
```

The API key is optional for keyless endpoints.

## Usage

### 1. NSE historical prices

```bash
python -m app.main ohlcv RELIANCE \
  --from-date 2025-01-01 \
  --to-date 2025-12-31
```

### 2. Adjusted historical prices

Requires a free API key.

```bash
python -m app.main ohlcv RELIANCE \
  --adjusted \
  --from-date 2025-01-01 \
  --to-date 2025-12-31
```

### 3. NSE full market snapshot

```bash
python -m app.main snapshot \
  --date 2025-11-14
```

### 4. Corporate actions

```bash
python -m app.main actions RELIANCE
```

### 5. Delivery data

Requires a free API key.

```bash
python -m app.main delivery RELIANCE \
  --from-date 2025-01-01 \
  --to-date 2025-12-31
```

### 6. NSE symbols

Requires a free API key.

```bash
python -m app.main symbols
```

### 7. Export to CSV

```bash
python -m app.main ohlcv RELIANCE \
  --from-date 2025-01-01 \
  --format csv \
  --output reliance_prices
```

### 8. Export to JSON

```bash
python -m app.main actions RELIANCE \
  --format json \
  --output reliance_actions
```

## API Provider

TejHQ

https://tejhq.dev/docs

API server:

https://api.tejhq.dev

## Security

Never commit your `.env` file or publish your API key.

## Disclaimer

Market data is provided for research and analysis.
Verify important values before making investment decisions.

