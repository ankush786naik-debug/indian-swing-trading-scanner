
import json
import os
import urllib.request
import urllib.error
import pandas as pd


def send_telegram_message(message):
    """Send a normal Telegram text message."""
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


def send_telegram_document(file_path, caption):
    """Send a CSV file as a Telegram document."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Telegram skipped: credentials unavailable.")
        return False

    boundary = "----NSEScannerBoundary"

    try:
        with open(file_path, "rb") as file:
            file_content = file.read()

        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
            f"{chat_id}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="caption"\r\n\r\n'
            f"{caption}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="document"; filename="nse_daily_signals.csv"\r\n'
            f"Content-Type: text/csv\r\n\r\n"
        ).encode("utf-8")

        body += file_content
        body += f"\r\n--{boundary}--\r\n".encode("utf-8")

        url = f"https://api.telegram.org/bot{token}/sendDocument"

        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}"
            },
            method="POST"
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))

            if result.get("ok"):
                print("Telegram CSV attachment sent successfully.")
                return True

            print(f"Telegram error: {result}")
            return False

    except Exception as error:
        print(f"Telegram document delivery failed: {error}")
        return False


def send_signal_alerts(buys, exits):
    """Combine BUY and EXIT signals into one CSV attachment."""

    frames = []

    if not buys.empty:
        buy_data = buys.copy()
        buy_data.insert(0, "signal", "BUY ENTRY")
        frames.append(buy_data)

    if not exits.empty:
        exit_data = exits.copy()
        exit_data.insert(0, "signal", "EXIT LONG")
        frames.append(exit_data)

    if not frames:
        print("No BUY or EXIT signals. Telegram attachment skipped.")
        return False

    combined = pd.concat(frames, ignore_index=True)

    file_path = "data/nse_daily_signals.csv"
    os.makedirs("data", exist_ok=True)

    combined.to_csv(file_path, index=False)

    buy_count = len(buys)
    exit_count = len(exits)

    caption = (
        "📊 NSE DAILY SCANNER RESULTS\n\n"
        f"🟢 BUY signals: {buy_count}\n"
        f"🔴 EXIT signals: {exit_count}\n\n"
        "Open the attached CSV in Excel or Google Sheets.\n"
        "Scanner output — verify before trading."
    )

    return send_telegram_document(file_path, caption)
    
