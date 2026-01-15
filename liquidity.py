import os
import requests
from typing import Dict, Any, List, Optional, Tuple


BINANCE_BASE = os.getenv("BINANCE_BASE", "https://api.binance.com")
BYBIT_BASE = os.getenv("BYBIT_BASE", "https://api.bybit.com")

# Пороги (можно управлять из Railway Variables)
# MAX_SPREAD_PCT = 1.0  → максимум спреда 1%
# MIN_NOTIONAL_5M = 50000  → минимум $объёма за 5m
# MIN_NOTIONAL_15M = 150000 → минимум $объёма за 15m
MAX_SPREAD_PCT = float(os.getenv("MAX_SPREAD_PCT", "1.0"))
MIN_NOTIONAL_5M = float(os.getenv("MIN_NOTIONAL_5M", "50000"))
MIN_NOTIONAL_15M = float(os.getenv("MIN_NOTIONAL_15M", "150000"))


def _sym_usdt(symbol: str) -> str:
    s = (symbol or "").upper().strip()
    return s if s.endswith("USDT") else s + "USDT"


def _safe_float(x: Any) -> Optional[float]:
    try:
        return float(x)
    except Exception:
        return None


def _spread_pct(bid: float, ask: float) -> float:
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return 999.0
    return ((ask - bid) / mid) * 100.0


def _notional_from_candles(candles: List[Dict[str, Any]], last_n: int = 1) -> float:
    """
    Оцениваем $объём: sum(volume * close) по последним N свечам.
    Это не идеально, но для раннего фильтра — топ.
    """
    if not candles:
        return 0.0
    chunk = candles[-last_n:] if len(candles) >= last_n else candles
    total = 0.0
    for c in chunk:
        v = _safe_float(c.get("v")) or 0.0
        close = _safe_float(c.get("c")) or 0.0
        total += v * close
    return total


def get_spread_binance(symbol: str) -> Optional[float]:
    """
    Binance best bid/ask spread % via /ticker/bookTicker
    """
    try:
        url = f"{BINANCE_BASE}/api/v3/ticker/bookTicker"
        r = requests.get(url, params={"symbol": _sym_usdt(symbol)}, timeout=10)
        r.raise_for_status()
        data = r.json() or {}
        bid = _safe_float(data.get("bidPrice"))
        ask = _safe_float(data.get("askPrice"))
        if not bid or not ask:
            return None
        return _spread_pct(bid, ask)
    except Exception:
        return None


def get_spread_bybit(symbol: str) -> Optional[float]:
    """
    Bybit spread % via v5 tickers (linear)
    """
    try:
        url = f"{BYBIT_BASE}/v5/market/tickers"
        r = requests.get(
            url,
            params={"category": "linear", "symbol": _sym_usdt(symbol)},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json() or {}
        result = data.get("result") or {}
        lst = result.get("list") or []
        if not lst:
            return None
        row = lst[0]
        bid = _safe_float(row.get("bid1Price"))
        ask = _safe_float(row.get("ask1Price"))
        if not bid or not ask:
            return None
        return _spread_pct(bid, ask)
    except Exception:
        return None


def liquidity_gate(
    symbol: str,
    market: str,  # "BINANCE" | "BYBIT"
    candles_5m: List[Dict[str, Any]],
    candles_15m: List[Dict[str, Any]],
) -> Tuple[bool, Dict[str, Any]]:
    """
    Возвращает (ok, metrics).
    ok=False → НЕ даём FIRST MOVE / CONFIRM (пока ликвидность плохая)
    """

    spread = None
    if market == "BINANCE":
        spread = get_spread_binance(symbol)
    elif market == "BYBIT":
        spread = get_spread_bybit(symbol)

    notional_5m = _notional_from_candles(candles_5m, last_n=1)
    notional_15m = _notional_from_candles(candles_15m, last_n=1)

    metrics = {
        "market": market,
        "spread_pct": spread,
        "notional_5m": notional_5m,
        "notional_15m": notional_15m,
        "max_spread_pct": MAX_SPREAD_PCT,
        "min_notional_5m": MIN_NOTIONAL_5M,
        "min_notional_15m": MIN_NOTIONAL_15M,
    }

    # если спред не смогли получить — считаем рискованно и не торгуем
    if spread is None:
        metrics["reason"] = "Нет данных по bid/ask (spread)"
        return False, metrics

    if spread > MAX_SPREAD_PCT:
        metrics["reason"] = f"Спред слишком большой: {spread:.2f}%"
        return False, metrics

    # объём — как дополнительный фильтр (чтобы не входить в пустоту)
    if notional_5m < MIN_NOTIONAL_5M and notional_15m < MIN_NOTIONAL_15M:
        metrics["reason"] = f"Слабая ликвидность: 5m=${notional_5m:,.0f}, 15m=${notional_15m:,.0f}"
        return False, metrics

    metrics["reason"] = "OK"
    return True, metrics
