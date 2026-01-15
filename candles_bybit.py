import os
import requests
from typing import List, Dict, Any


BYBIT_BASE = os.getenv("BYBIT_BASE", "https://api.bybit.com")


def _sym(symbol: str) -> str:
    """
    Приводим к стандарту Bybit (spot/linear чаще TOKENUSDT).
    """
    s = symbol.upper().strip()
    if s.endswith("USDT"):
        return s
    return s + "USDT"


def _fetch_kline_v5(symbol: str, interval: str, limit: int = 200) -> List[List[Any]]:
    """
    Bybit v5 market/kline
    interval: "5" или "15"
    """
    url = f"{BYBIT_BASE}/v5/market/kline"
    params = {
        "category": "linear",      # чаще всего новые токены появляются в linear/perp
        "symbol": _sym(symbol),
        "interval": interval,
        "limit": int(limit),
    }
    try:
        r = requests.get(url, params=params, timeout=12)
        r.raise_for_status()
        data = r.json() or {}
        result = (data.get("result") or {})
        lst = result.get("list") or []
        return lst
    except Exception:
        return []


def _normalize_bybit_list(lst: List[List[Any]]) -> List[Dict[str, Any]]:
    """
    Bybit v5 list format:
    [startTime, open, high, low, close, volume, turnover]
    Обычно приходит в обратном порядке (новые -> старые), развернём.
    """
    out: List[Dict[str, Any]] = []
    try:
        lst = list(reversed(lst))
    except Exception:
        pass

    for k in lst:
        try:
            out.append({
                "o": float(k[1]),
                "h": float(k[2]),
                "l": float(k[3]),
                "c": float(k[4]),
                "v": float(k[5]),
            })
        except Exception:
            continue
    return out


def get_candles_5m(symbol: str, limit: int = 200) -> List[Dict[str, Any]]:
    lst = _fetch_kline_v5(symbol, interval="5", limit=limit)
    return _normalize_bybit_list(lst)


def get_candles_15m(symbol: str, limit: int = 200) -> List[Dict[str, Any]]:
    lst = _fetch_kline_v5(symbol, interval="15", limit=limit)
    return _normalize_bybit_list(lst)

