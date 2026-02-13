# crowd_engine.py

from typing import List, Dict, Any


def crowd_engine_ok(candles: List[Dict[str, Any]]) -> bool:
    """
    PRO CROWD ENGINE
    Определяет момент когда толпа начинает входить.

    Не использует funding/OI — работает по свечам.
    """

    if not candles or len(candles) < 12:
        return False

    try:
        volumes = [float(c[5]) for c in candles]
        highs = [float(c[2]) for c in candles]
        lows = [float(c[3]) for c in candles]
        closes = [float(c[4]) for c in candles]
    except Exception:
        return False

    # последние 3 свечи
    last_vol = volumes[-1]
    prev_vol = volumes[-2]

    avg_vol = sum(volumes[:-3]) / max(len(volumes[:-3]), 1)

    # 1️⃣ объём толпы
    volume_break = last_vol > avg_vol * 2.2

    # 2️⃣ ускорение диапазона
    last_range = highs[-1] - lows[-1]
    prev_range = highs[-2] - lows[-2]

    range_expand = last_range > prev_range * 1.3

    # 3️⃣ закрытия вверх
    bullish_flow = closes[-1] >= closes[-2] >= closes[-3]

    # 4️⃣ нет сильного отката
    pullback_ok = (closes[-1] - lows[-1]) > (last_range * 0.5)

    return volume_break and range_expand and bullish_flow and pullback_ok
