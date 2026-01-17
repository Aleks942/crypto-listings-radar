# detect_trading.py
import requests


BINANCE_EXCHANGE_INFO = "https://api.binance.com/api/v3/exchangeInfo"
BYBIT_SPOT_SYMBOLS = "https://api.bybit.com/v5/market/instruments-info?category=spot"
BYBIT_LINEAR_SYMBOLS = "https://api.bybit.com/v5/market/instruments-info?category=linear"


def _norm_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    return s


def check_binance(symbol: str) -> bool:
    """
    Binance spot: ищем пару SYMBOLUSDT
    """
    sym = _norm_symbol(symbol)
    if not sym:
        return False

    pair = f"{sym}USDT"
    try:
        r = requests.get(BINANCE_EXCHANGE_INFO, timeout=10)
        r.raise_for_status()
        data = r.json()
        for x in data.get("symbols", []):
            if x.get("symbol") == pair and x.get("status") == "TRADING":
                return True
        return False
    except Exception:
        return False


def check_bybit(symbol: str) -> bool:
    """
    Bybit spot: ищем пару SYMBOLUSDT
    """
    sym = _norm_symbol(symbol)
    if not sym:
        return False

    pair = f"{sym}USDT"
    try:
        url = BYBIT_SPOT_SYMBOLS
        # bybit отдаёт списками по страницам — но обычно на практике и так находит
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json() or {}
        result = data.get("result") or {}
        items = result.get("list") or []
        for x in items:
            if (x.get("symbol") or "").upper() == pair and (x.get("status") or "").lower() == "trading":
                return True
        return False
    except Exception:
        return False


def check_bybit_linear(symbol: str) -> bool:
    """
    Bybit perp (linear): ищем SYMBOLUSDT в category=linear
    """
    sym = _norm_symbol(symbol)
    if not sym:
        return False

    pair = f"{sym}USDT"
    try:
        r = requests.get(BYBIT_LINEAR_SYMBOLS, timeout=10)
        r.raise_for_status()
        data = r.json() or {}
        result = data.get("result") or {}
        items = result.get("list") or []
        for x in items:
            if (x.get("symbol") or "").upper() == pair and (x.get("status") or "").lower() == "trading":
                return True
        return False
    except Exception:
        return False

