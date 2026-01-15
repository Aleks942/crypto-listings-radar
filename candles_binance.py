import os
import time
import requests
from typing import List, Dict, Any


BINANCE_BASE = os.getenv("BINANCE_BASE", "https://api.binance.com")


def _sym(symbol: str) -> str:
    """
    Приводим к стандарту Binance: TOKENUSDT.
    Если уже содержит USDT — оставляем.
    """
    s = symbol.upper().strip()
    if s.endswith("USDT"):
        return s
    return s + "USDT"


def _fetch_klines(symbol: str, interval: str, limit: int = 200) -> List[List[Any]]:
    url = f"{BINANCE_BASE}/api/v3/klines"
    params = {
        "symbol": _sym(symbol),
        "interval": interval,
        "limit": int(limit),
    }
    try:
        r = requests.get(url, params=params, timeout=12)
        r.raise_for_status()
        return r.json() or []
    except Exception:
        return []


def _normalize_klines(klines: List[List[Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for k in klines:
        # kline format:
        # 0 open_time, 1 open, 2 high, 3 low, 4 close, 5 volume, ...
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
    kl = _fetch_klines(symbol, interval="5m", limit=limit)
    return _normalize_klines(kl)


def get_candles_15m(symbol: str, limit: int = 200) -> List[Dict[str, Any]]:
    kl = _fetch_klines(symbol, interval="15m", limit=limit)
    return _normalize_klines(kl)

