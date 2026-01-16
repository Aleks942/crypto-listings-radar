import requests


BINANCE_EXCHANGE_INFO = "https://api.binance.com/api/v3/exchangeInfo"
BYBIT_SPOT_SYMBOLS    = "https://api.bybit.com/v5/market/instruments-info?category=spot"
BYBIT_LINEAR_SYMBOLS  = "https://api.bybit.com/v5/market/instruments-info?category=linear"


def _norm_symbol(sym: str) -> str:
    return (sym or "").strip().upper()


def check_binance(symbol: str) -> bool:
    """
    Проверка: есть ли символ на Binance SPOT (пара SYMBOLUSDT).
    """
    s = _norm_symbol(symbol)
    if not s:
        return False

    try:
        r = requests.get(BINANCE_EXCHANGE_INFO, timeout=10)
        r.raise_for_status()
        data = r.json()
        target = f"{s}USDT"

        for it in data.get("symbols", []):
            if it.get("symbol") == target and it.get("status") == "TRADING":
                return True
        return False
    except Exception:
        return False


def check_bybit(symbol: str) -> bool:
    """
    Проверка: есть ли символ на Bybit SPOT (пара SYMBOLUSDT).
    """
    s = _norm_symbol(symbol)
    if not s:
        return False

    try:
        r = requests.get(BYBIT_SPOT_SYMBOLS, timeout=10)
        r.raise_for_status()
        data = r.json()

        target = f"{s}USDT"
        items = ((data.get("result") or {}).get("list") or [])

        for it in items:
            if (it.get("symbol") or "").upper() == target:
                st = (it.get("status") or "").upper()
                # Bybit иногда возвращает "Trading" / "TRADING" / "ONLINE"
                if st in ("TRADING", "ONLINE", "TRADABLE", "1", ""):
                    return True
                # если status непонятный — всё равно считаем, что инструмент существует
                return True

        return False
    except Exception:
        return False


def check_bybit_linear(symbol: str) -> bool:
    """
    Проверка: есть ли символ на Bybit PERP (linear), обычно это SYMBOLUSDT.
    """
    s = _norm_symbol(symbol)
    if not s:
        return False

    try:
        r = requests.get(BYBIT_LINEAR_SYMBOLS, timeout=10)
        r.raise_for_status()
        data = r.json()

        target = f"{s}USDT"
        items = ((data.get("result") or {}).get("list") or [])

        for it in items:
            if (it.get("symbol") or "").upper() == target:
                st = (it.get("status") or "").upper()
                if st in ("TRADING", "ONLINE", "TRADABLE", "1", ""):
                    return True
                return True

        return False
    except Exception:
        return False

