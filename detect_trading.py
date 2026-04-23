import requests


HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def _safe_get(url, timeout=10):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None
    return None


# ================= BINANCE =================
def check_binance(symbol: str) -> bool:
    data = _safe_get("https://api.binance.com/api/v3/exchangeInfo")
    if not data or "symbols" not in data:
        return False

    target = f"{symbol.upper()}USDT"
    for item in data["symbols"]:
        if item.get("symbol") == target and item.get("status") == "TRADING":
            return True
    return False


# ================= BYBIT SPOT =================
def check_bybit(symbol: str) -> bool:
    data = _safe_get("https://api.bybit.com/v5/market/instruments-info?category=spot")
    try:
        items = data["result"]["list"]
    except Exception:
        return False

    target = f"{symbol.upper()}USDT"
    for item in items:
        if item.get("symbol") == target and item.get("status") == "Trading":
            return True
    return False


# ================= BYBIT LINEAR =================
def check_bybit_linear(symbol: str) -> bool:
    data = _safe_get("https://api.bybit.com/v5/market/instruments-info?category=linear")
    try:
        items = data["result"]["list"]
    except Exception:
        return False

    target = f"{symbol.upper()}USDT"
    for item in items:
        if item.get("symbol") == target and item.get("status") == "Trading":
            return True
    return False


# ================= MEXC =================
def check_mexc(symbol: str) -> bool:
    data = _safe_get("https://api.mexc.com/api/v3/exchangeInfo")
    if not data or "symbols" not in data:
        return False

    target = f"{symbol.upper()}USDT"
    for item in data["symbols"]:
        if item.get("symbol") == target and item.get("status") == "1":
            return True
    return False


# ================= GATE =================
def check_gate(symbol: str) -> bool:
    data = _safe_get("https://api.gateio.ws/api/v4/spot/currency_pairs")
    if not isinstance(data, list):
        return False

    target = f"{symbol.upper()}_USDT"
    for item in data:
        if item.get("id") == target and item.get("trade_status") == "tradable":
            return True
    return False


# ================= BITGET =================
def check_bitget(symbol: str) -> bool:
    data = _safe_get("https://api.bitget.com/api/v2/spot/public/symbols")
    try:
        items = data["data"]
    except Exception:
        return False

    target = f"{symbol.upper()}USDT"
    for item in items:
        if item.get("symbol") == target and item.get("status") == "online":
            return True
    return False


# ================= KUCOIN =================
def check_kucoin(symbol: str) -> bool:
    data = _safe_get("https://api.kucoin.com/api/v2/symbols")
    try:
        items = data["data"]
    except Exception:
        return False

    target = f"{symbol.upper()}-USDT"
    for item in items:
        if item.get("symbol") == target and item.get("enableTrading") is True:
            return True
    return False
