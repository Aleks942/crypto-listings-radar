import requests

BINANCE_INFO = "https://api.binance.com/api/v3/exchangeInfo"
BYBIT_INFO = "https://api.bybit.com/v5/market/instruments-info?category=spot"


def _safe_get(url: str):
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def check_binance(symbol: str) -> bool:
    data = _safe_get(BINANCE_INFO)
    if not data:
        return False

    target = f"{symbol.upper()}USDT"
    for s in data.get("symbols", []):
        if s.get("symbol") == target and s.get("status") == "TRADING":
            return True
    return False


def check_bybit(symbol: str) -> bool:
    data = _safe_get(BYBIT_INFO)
    if not data:
        return False

    target = f"{symbol.upper()}USDT"
    for s in (data.get("result", {}).get("list") or []):
        if s.get("symbol") == target and s.get("status") == "Trading":
            return True
    return False
