import requests

BINANCE = "https://api.binance.com"
BYBIT = "https://api.bybit.com"


def _pair(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    return s if s.endswith("USDT") else f"{s}USDT"


# -------------------------
# BINANCE
# -------------------------

def binance_symbol_exists(symbol: str) -> bool:
    """
    Быстрая проверка: есть ли символ на Binance (обычно spot).
    """
    try:
        sym = _pair(symbol)
        url = f"{BINANCE}/api/v3/ticker/price"
        r = requests.get(url, params={"symbol": sym}, timeout=8)
        return r.status_code == 200
    except Exception:
        return False


def check_binance(symbol: str) -> bool:
    return binance_symbol_exists(symbol)


# -------------------------
# BYBIT (spot + linear/perp)
# -------------------------

def bybit_symbol_exists(category: str, symbol: str) -> bool:
    """
    category: 'spot' | 'linear'
    """
    try:
        sym = _pair(symbol)
        url = f"{BYBIT}/v5/market/tickers"
        r = requests.get(url, params={"category": category, "symbol": sym}, timeout=8)
        if r.status_code != 200:
            return False
        data = r.json()
        if str(data.get("retCode")) != "0":
            return False
        lst = (data.get("result") or {}).get("list") or []
        return len(lst) > 0
    except Exception:
        return False


def check_bybit(symbol: str) -> bool:
    """
    True если есть либо spot, либо linear (perp).
    """
    return bybit_symbol_exists("spot", symbol) or bybit_symbol_exists("linear", symbol)

