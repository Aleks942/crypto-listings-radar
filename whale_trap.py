# whale_trap.py

from typing import List


def whale_trap_detect(candles: List[list]) -> bool:
    """
    True  -> обнаружена возможная разгрузка китов
    False -> всё ок

    candles формат:
    [ts, open, high, low, close, volume]
    """

    if not candles or len(candles) < 5:
        return False

    try:
        last = candles[-1]
        prev = candles[-2]

        o = float(last[1])
        h = float(last[2])
        l = float(last[3])
        c = float(last[4])
        v = float(last[5])

        po = float(prev[1])
        pc = float(prev[4])
        pv = float(prev[5])
    except Exception:
        return False

    body = abs(c - o)
    full = max(1e-12, h - l)

    upper_wick = h - max(c, o)

    # 🔴 признаки разгрузки
    long_upper_wick = upper_wick > body * 1.2
    weak_close = c < (l + full * 0.6)
    volume_spike = v > pv * 1.3

    if long_upper_wick and weak_close and volume_spike:
        return True

    return False
