import requests

BASE_URL = "https://api.binance.com"

def get_candles_5m(symbol: str, limit: int = 30) -> list[dict]:
    url = f"{BASE_URL}/api/v3/klines"
    params = {
        "symbol": f"{symbol}USDT",
        "interval": "5m",
        "limit": limit,
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []

    if not isinstance(data, list):
        return []

    candles = []
    for k in data:
        candles.append({
            "o": float(k[1]),
            "h": float(k[2]),
            "l": float(k[3]),
            "c": float(k[4]),
            "v": float(k[5]),
        })

    return candles
