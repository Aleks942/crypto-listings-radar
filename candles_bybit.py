import requests

BASE_URL = "https://api.bybit.com"

def get_candles_5m(symbol: str, limit: int = 30) -> list[dict]:
    """
    Пытаемся взять SPOT свечи Bybit для пары SYMBOLUSDT (например, BTCUSDT).
    Возвращаем список свечей в формате confirm-engine:
    [{"o":..,"h":..,"l":..,"c":..,"v":..}, ...] (старые -> новые)
    """
    url = f"{BASE_URL}/v5/market/kline"
    params = {
        "category": "spot",
        "symbol": f"{symbol}USDT",
        "interval": "5",
        "limit": limit,
    }

    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()

    if data.get("retCode") != 0:
        return []

    klines = (data.get("result") or {}).get("list") or []
    if not klines:
        return []

    candles = []
    # Bybit отдаёт новые -> старые, нам надо старые -> новые
    for k in reversed(klines):
        # формат: [startTime, open, high, low, close, volume, turnover]
        candles.append({
            "o": float(k[1]),
            "h": float(k[2]),
            "l": float(k[3]),
            "c": float(k[4]),
            "v": float(k[5]),
        })

    return candles
