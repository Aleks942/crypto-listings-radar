import os
import time
import requests
from typing import List, Dict, Any

BYBIT_BASE = "https://api.bybit.com"
BYBIT_KLINES = f"{BYBIT_BASE}/v5/market/kline"

DEFAULT_LIMIT_5M = int(os.getenv("BYBIT_LIMIT_5M", "120"))
DEFAULT_LIMIT_15M = int(os.getenv("BYBIT_LIMIT_15M", "120"))

HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "10"))


def _sym(symbol: str) -> str:
    # Bybit spot/perp часто: SYMBOLUSDT
    s = (symbol or "").strip().upper()
    if s.endswith("USDT"):
        return s
    return f"{s}USDT"


def _fetch_klines(symbol: str, interval_min: int, limit: int) -> List[Dict[str, Any]]:
    params = {
        "category": "spot",
        "symbol": _sym(symbol),
        "interval": str(interval_min),  # minutes as string: "5", "15"
        "limit": int(limit),
    }
    r = requests.get(BYBIT_KLINES, params=params, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    js = r.json()

    # v5 response: {"retCode":0,"result":{"list":[[ts,open,high,low,close,volume,turnover],...]}}
    result = (js.get("result") or {})
    rows = result.get("list") or []

    out = []
    for row in rows:
        # row: [startTime, open, high, low, close, volume, turnover]
        ts_ms = int(row[0])
        out.append({
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
            "ts": ts_ms / 1000.0,
        })

    # Bybit часто отдаёт от новых к старым — приводим к старые->новые
    out.sort(key=lambda x: x["ts"])
    return out


def get_candles_5m(symbol: str, limit: int = DEFAULT_LIMIT_5M) -> List[Dict[str, Any]]:
    return _fetch_klines(symbol, 5, limit)


def get_candles_15m(symbol: str, limit: int = DEFAULT_LIMIT_15M) -> List[Dict[str, Any]]:
    return _fetch_klines(symbol, 15, limit)


