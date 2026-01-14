from typing import List, Dict


def confirm_light_signal(candles: List[Dict]) -> bool:
    """
    CONFIRM-LIGHT (MVP):
    - минимум 8 свечей 15m
    - коррекция 20–40% от импульса
    - удержание выше середины импульса
    """

    if not candles or len(candles) < 8:
        return False

    highs = [c["h"] for c in candles]
    lows = [c["l"] for c in candles]

    hi = max(highs)
    lo = min(lows)
    if lo <= 0:
        return False

    move = hi - lo
    if move <= 0:
        return False

    last = candles[-1]
    retr = (hi - last["c"]) / move

    # коррекция 20–40%
    if not (0.20 <= retr <= 0.40):
        return False

    mid = lo + 0.5 * move
    return last["c"] > mid
