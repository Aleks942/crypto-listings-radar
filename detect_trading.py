import requests

BASE = "https://api.bybit.com"


def _pair(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    return s if s.endswith("USDT") else f"{s}USDT"


def check_binance(symbol: str) -> bool:
    # оставь как было у тебя (если binance уже работает)
    # если хочешь — я дам и binance-версию тоже, но сейчас не трогаем.
    try:
        sym = _pair(symbol)
        url = "https://api.binance.com/api/v3/ticker/price"
        r = requests.get(url, params={"symbol": sym}, timeout=8)
        return r.status_code == 200
    except Exception:
        return False


def _bybit_ticker_exists(category: str, symbol: str) -> bool:
    sym = _pair(symbol)
    url = f"{BASE}/v5/market/tickers"
    params = {"category": category, "symbol": sym}
    r = requests.get(url, params=params, timeout=8)
    if r.status_code != 200:
        return False
    data = r.json()
    if str(data.get("retCode")) != "0":
        return False
    result = data.get("result") or {}
    lst = result.get("list") or []
    return len(lst) > 0


def check_bybit(symbol: str) -> bool:
    # spot OR linear (perp)
    try:
        if _bybit_ticker_exists("spot", symbol):
            return True
        if _bybit_ticker_exists("linear", symbol):
            return True
        return False
    except Exception:
        return False

