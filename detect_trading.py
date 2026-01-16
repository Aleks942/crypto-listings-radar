import requests


# -------------------------
# BINANCE SPOT
# -------------------------
def check_binance(symbol: str) -> bool:
    """
    Проверяет, есть ли SPOT пара SYMBOLUSDT на Binance.
    """
    s = (symbol or "").upper().strip()
    if not s:
        return False

    try:
        url = "https://api.binance.com/api/v3/exchangeInfo"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        pair = f"{s}USDT"

        for item in data.get("symbols", []):
            if item.get("symbol") == pair and item.get("status") == "TRADING":
                return True
        return False
    except Exception:
        return False


# -------------------------
# BYBIT SPOT
# -------------------------
def check_bybit(symbol: str) -> bool:
    """
    Проверяет, есть ли SPOT пара SYMBOLUSDT на Bybit.
    """
    s = (symbol or "").upper().strip()
    if not s:
        return False

    try:
        url = "https://api.bybit.com/v5/market/instruments-info"
        params = {"category": "spot", "limit": 1000}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        pair = f"{s}USDT"
        items = (((data or {}).get("result") or {}).get("list") or [])

        for it in items:
            if it.get("symbol") == pair and (it.get("status") in ("Trading", "trading", "TRADING")):
                return True

        # иногда status нет — тогда достаточно факта наличия пары
        for it in items:
            if it.get("symbol") == pair:
                return True

        return False
    except Exception:
        return False


# -------------------------
# BYBIT LINEAR PERP (USDT)
# -------------------------
def check_bybit_linear(symbol: str) -> bool:
    """
    Проверяет, есть ли USDT Perpetual (linear) контракт SYMBOLUSDT на Bybit.
    Это даёт больше шансов поймать новые монеты, которые сначала выходят как perp.
    """
    s = (symbol or "").upper().strip()
    if not s:
        return False

    try:
        url = "https://api.bybit.com/v5/market/instruments-info"
        params = {"category": "linear", "limit": 1000}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        pair = f"{s}USDT"
        items = (((data or {}).get("result") or {}).get("list") or [])

        for it in items:
            if it.get("symbol") == pair and (it.get("status") in ("Trading", "trading", "TRADING")):
                return True

        # fallback: если статус не отдали — достаточно наличия инструмента
        for it in items:
            if it.get("symbol") == pair:
                return True

        return False
    except Exception:
        return False

