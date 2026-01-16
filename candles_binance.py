import os
import time
import requests
from typing import List, Dict, Any

BINANCE_BASE = "https://api.binance.com"
BINANCE_SPOT_EXCHANGE_INFO = f"{BINANCE_BASE}/api/v3/exchangeInfo"
BINANCE_KLINES = f"{BINANCE_BASE}/api/v3/klines"

# сколько свечей брать
DEFAULT_LIMIT_5M = int(os.getenv("BINANCE_LIMIT_5M", "120"))
DEFAULT_LIMIT_15M = int(os.getenv("BINANCE_LIMIT_15M", "120"))

# таймауты
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "10"))


def _sym(symbol: str) -> str:
    # Binance spot: SYMBOLUSDT
    s = (symbol or "").strip().upper()
    if s.endswith("USDT"):
        return s
    return f"{s}USDT"


def _fetch_klines(symbol: str, interval: str, limit: int) -> List[Dict[str, Any]]:
    params = {"symbol": _sym(symbol), "interval": interval, "limit": int(limit)}
    r = requests.get(BINANCE_KLINES, params=params, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    data = r.json()

    out = []
    for k in data:
        # kline format:
        # 0 openTime, 1 open, 2 high, 3 low, 4 close, 5 volume, ...
        out.append({
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "ts": int(k[0]) / 1000.0,
        })
    return out


def get_candles_5m(symbol: str, limit: int = DEFAULT_LIMIT_5M) -> List[Dict[str, Any]]:
    return _fetch_klines(symbol, "5m", limit)


def get_candles_15m(symbol: str, limit: int = DEFAULT_LIMIT_15M) -> List[Dict[str, Any]]:
    return _fetch_klines(symbol, "15m", limit)

