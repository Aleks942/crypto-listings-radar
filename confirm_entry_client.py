import os
import requests
import time

CONFIRM_ENTRY_URL = os.getenv("CONFIRM_ENTRY_URL")  # например: https://confirm-entry.up.railway.app/webhook/listing
CONFIRM_ENTRY_TIMEOUT = float(os.getenv("CONFIRM_ENTRY_TIMEOUT", "5"))

def send_to_confirm_entry(symbol, exchange, tf, candles, mode_hint="CONFIRM_LIGHT"):
    if not CONFIRM_ENTRY_URL:
        return False, "no_url"

    payload = {
        "symbol": symbol,
        "exchange": exchange,
        "tf": tf,
        "mode_hint": mode_hint,
        "candles": [
            {
                "o": c["o"],
                "h": c["h"],
                "l": c["l"],
                "c": c["c"],
                "v": c["v"],
            }
            for c in candles
        ],
    }

    try:
        r = requests.post(
            CONFIRM_ENTRY_URL,
            json=payload,
            timeout=CONFIRM_ENTRY_TIMEOUT,
        )
        if r.status_code == 200:
            return True, "sent"
        return False, f"http_{r.status_code}"
    except Exception as e:
        return False, str(e)
