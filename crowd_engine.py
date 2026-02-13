# crowd_engine.py

from typing import List, Dict, Any


# ==============================
# 🧠 CROWD ENGINE PRO (основа)
# ==============================

def crowd_engine_ok(candles: List[Dict[str, Any]]) -> bool:
    """
    Определяет момент когда толпа начинает входить.
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

    last_vol = volumes[-1]
    avg_vol = sum(volumes[:-3]) / max(len(volumes[:-3]), 1)

    volume_break = last_vol > avg_vol * 2.2

    last_range = highs[-1] - lows[-1]
    prev_range = highs[-2] - lows[-2]

    range_expand = last_range > prev_range * 1.3

    bullish_flow = closes[-1] >= closes[-2] >= closes[-3]

    pullback_ok = (closes[-1] - lows[-1]) > (last_range * 0.5)

    return volume_break and range_expand and bullish_flow and pullback_ok


# ==================================
# 🚀 CROWD ENGINE V2 — ВТОРАЯ ВОЛНА
# ==================================

def crowd_wave_v2(candles: List[Dict[str, Any]]) -> bool:

    if not candles or len(candles) < 20:
        return False

    try:
        volumes = [float(c[5]) for c in candles]
        closes = [float(c[4]) for c in candles]
    except Exception:
        return False

    avg_vol = sum(volumes[:-5]) / max(len(volumes[:-5]), 1)

    first_spike = max(volumes[-15:-10]) > avg_vol * 2
    pullback = closes[-7] < closes[-10]
    second_spike = volumes[-1] > avg_vol * 1.8

    return first_spike and pullback and second_spike


# ==================================
# ⚡ FAST SECOND WAVE — МГНОВЕННАЯ
# ==================================

def second_wave_detect(candles: List[Dict[str, Any]]) -> bool:

    if not candles or len(candles) < 8:
        return False

    try:
        volumes = [float(c[5]) for c in candles]
    except Exception:
        return False

    v1 = volumes[-4]
    v2 = volumes[-3]
    v3 = volumes[-2]
    v4 = volumes[-1]

    first_push = v2 > v1 * 1.6
    pullback = v3 < v2 * 0.8
    second_push = v4 > v3 * 1.8

    return first_push and pullback and second_push


# ==================================
# 🧠 SMART SILENCE FILTER
# ==================================

def smart_silence_filter(candles: List[Dict[str, Any]]) -> bool:

    if not candles or len(candles) < 10:
        return False

    try:
        volumes = [float(c[5]) for c in candles]
    except Exception:
        return False

    avg = sum(volumes[:-3]) / max(len(volumes[:-3]), 1)

    spike = volumes[-1] > avg * 2
    continuation = volumes[-2] > avg * 1.2

    return spike and continuation


# ==================================
# 🔥 ОБЩИЙ CROWD SIGNAL (ФИНАЛ)
# ==================================

def crowd_engine_signal(candles: List[Dict[str, Any]]) -> bool:
    """
    Финальный сигнал толпы:

    PRO + V2 + FAST SECOND WAVE
    + SMART SILENCE FILTER
    """

    try:
        pro_ok = crowd_engine_ok(candles)
        v2_ok = crowd_wave_v2(candles)
        fast_ok = second_wave_detect(candles)
        silence_ok = smart_silence_filter(candles)

        return (pro_ok or v2_ok or fast_ok) and silence_ok

    except Exception:
        return False
