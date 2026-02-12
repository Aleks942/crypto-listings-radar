# sharp_filters.py
from typing import List, Dict


def _candle_body(c):
    # ожидается [time, open, high, low, close, volume]
    o = float(c[1])
    cl = float(c[4])
    return abs(cl - o)


def _candle_range(c):
    h = float(c[2])
    l = float(c[3])
    return abs(h - l)


# =====================================
# 1️⃣ Thin Liquidity filter
# =====================================
def thin_liquidity(candles: List[List]) -> bool:
    """
    True = рынок тонкий → блокируем сигнал
    """
    if len(candles) < 5:
        return True

    bodies = [_candle_body(c) for c in candles[-5:]]
    ranges = [_candle_range(c) for c in candles[-5:]]

    avg_body = sum(bodies) / len(bodies)
    avg_range = sum(ranges) / len(ranges)

    if avg_range == 0:
        return True

    ratio = avg_body / avg_range

    # если тело слишком маленькое относительно тени
    return ratio < 0.25


# =====================================
# 2️⃣ Manipulation pump filter
# =====================================
def manipulation_pump(candles: List[List]) -> bool:
    """
    True = подозрительный памп
    """
    if not candles:
        return True

    last = candles[-1]
    o = float(last[1])
    cl = float(last[4])

    if o == 0:
        return True

    change = (cl - o) / o * 100.0

    # SHARP режим — жёстко
    return change > 60


# =====================================
# 3️⃣ Exchange quality filter
# =====================================
def bad_exchange_only(trading_info: Dict) -> bool:
    """
    True = плохая биржевая структура
    """
    binance = trading_info.get("binance")
    bybit_spot = trading_info.get("bybit_spot")
    bybit_linear = trading_info.get("bybit_linear")

    # если только linear — опасно
    if bybit_linear and not (binance or bybit_spot):
        return True

    return False


# =====================================
# MASTER FILTER
# =====================================
def sharp_hunter_ok(candles_5m: List[List], trading_info: Dict) -> bool:

    if bad_exchange_only(trading_info):
        return False

    if thin_liquidity(candles_5m):
        return False

    if manipulation_pump(candles_5m):
        return False

    return True
