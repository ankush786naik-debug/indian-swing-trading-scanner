import json
import os
import urllib.request
import urllib.error


def send_telegram_message(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Telegram skipped: credentials unavailable.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message
    }).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result.get("ok", False)
    except Exception as error:
        print(f"Telegram delivery failed: {error}")
        return False


def send_signal_alerts(buys, exits):
    for _, row in buys.iterrows():
        message = (
            "🟢 NSE BUY ENTRY\n\n"
            f"Stock: {row.get('symbol', '')}\n"
            f"Entry: ₹{row.get('entry_price', '')}\n"
            f"Stop Loss: ₹{row.get('stop_loss', '')}\n"
            f"Target 1: ₹{row.get('target_1', '')}\n"
            f"Target 2: ₹{row.get('target_2', '')}\n"
            f"RSI: {row.get('rsi', '')}\n"
            f"ADX: {row.get('adx', '')}\n"
            f"Bullish Score: {row.get('bullish_score', '')}\n"
            "\nScanner signal — verify before trading."
        )
        send_telegram_message(message)

    for _, row in exits.iterrows():
        message = (
            "🔴 NSE EXIT LONG\n\n"
            f"Stock: {row.get('symbol', '')}\n"
            f"Price: ₹{row.get('price', '')}\n"
            "\nScanner exit signal — review your position."
        )
        send_telegram_message(message)
