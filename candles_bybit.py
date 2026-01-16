import requests
from typing import List, Dict, Any, Optional

BASE = "https://api.bybit.com"


def _pair(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    return s if s.endswith("USDT") else f"{s}USDT"


def _fetch_kline(category: str, symbol: str, interval: str, limit: int = 200) -> List[Dict[str, Any]]:
    """
    Bybit v5 klines:
    /v5/market/kline?category=spot|linear&symbol=FOGOUSDT&interval=5&limit=200
    result.list: [ [start, open, high, low, close, volume, turnover], ... ]
    """
    sym = _pair(symbol)

    url = f"{BASE}/v5/market/kline"
    params = {
        "category": category,
        "symbol": sym,
        "interval": str(interval),  # "5", "15", ...
        "limit": str(limit),
    }

    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()

    if str(data.get("retCode")) != "0":
        return []

    result = data.get("result") or {}
    rows = result.get("list") or []
    if not rows:
        return []

    # В Bybit list обычно в обратном порядке (последние первые) — разворачиваем к старым->новым
    rows = list(reversed(rows))

    out: List[Dict[str, Any]] = []
    for row in rows:
        # row: [startTime, open, high, low, close, volume, turnover]
        try:
            ts = int(row[0])
            o = float(row[1])
            h = float(row[2])
            l = float(row[3])
            c = float(row[4])
            v = float(row[5])
        except Exception:
            continue

        # Делаем “двойной формат” ключей — чтобы не ломалось ни в score_engine, ни в entry_window
        out.append({
            "t": ts,
            "o": o, "h": h, "l": l, "c": c, "v": v,
            "open": o, "high": h, "low": l, "close": c, "volume": v,
        })

    return out


def _get_candles_with_fallback(symbol: str, interval: str, limit: int = 200) -> List[Dict[str, Any]]:
    # 1) пробуем spot
    spot = _fetch_kline("spot", symbol, interval, limit=limit)
    if spot:
        return spot

    # 2) fallback на linear (perp)
    linear = _fetch_kline("linear", symbol, interval, limit=limit)
    return linear


def get_candles_5m(symbol: str, limit: int = 200) -> List[Dict[str, Any]]:
    return _get_candles_with_fallback(symbol, interval="5", limit=limit)


def get_candles_15m(symbol: str, limit: int = 200) -> List[Dict[str, Any]]:
    return _get_candles_with_fallback(symbol, interval="15", limit=limit)
