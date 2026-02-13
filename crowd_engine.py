# crowd_engine.py

from typing import List, Dict, Any


# ==============================
# 🧠 CROWD ENGINE PRO
# ==============================

def crowd_engine_ok(candles: List[Dict[str, Any]]) -> bool:

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
# 🚀 CROWD WAVE V2
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
# ⚡ FAST SECOND WAVE
# ==================================

def second_wave_detect(candles: List[Dict[str, Any]]) -> bool:

    if not candles or len(candles) < 8:
        return False

    try:
        volumes = [float(c[5]) for c in candles]
    except Exception:
        return False

    v1, v2, v3, v4 = volumes[-4], volumes[-3], volumes[-2], volumes[-1]

    return v2 > v1 * 1.6 and v3 < v2 * 0.8 and v4 > v3 * 1.8


# ==================================
# 💥 PRESSURE BUILD
# ==================================

def crowd_pressure_build(candles: List[Dict[str, Any]]) -> bool:

    if not candles or len(candles) < 6:
        return False

    try:
        volumes = [float(c[5]) for c in candles]
    except Exception:
        return False

    return volumes[-1] > volumes[-2] > volumes[-3]


# ==================================
# ⚡ EARLY MOMENTUM
# ==================================

def early_momentum_shift(candles: List[Dict[str, Any]]) -> bool:

    if not candles or len(candles) < 5:
        return False

    try:
        highs = [float(c[2]) for c in candles]
        volumes = [float(c[5]) for c in candles]
    except Exception:
        return False

    return highs[-1] > highs[-2] > highs[-3] and volumes[-1] > volumes[-2]


# ==================================
# 🧨 LIQUIDITY COMPRESSION
# ==================================

def liquidity_compression(candles: List[Dict[str, Any]]) -> bool:

    if not candles or len(candles) < 6:
        return False

    try:
        highs = [float(c[2]) for c in candles]
        lows = [float(c[3]) for c in candles]
    except Exception:
        return False

    r1 = highs[-3] - lows[-3]
    r2 = highs[-2] - lows[-2]
    r3 = highs[-1] - lows[-1]

    return r3 < r2 < r1


# ==================================
# 🔇 SMART SILENCE FILTER
# ==================================

def smart_silence_filter(candles: List[Dict[str, Any]]) -> bool:

    if not candles or len(candles) < 10:
        return False

    try:
        volumes = [float(c[5]) for c in candles]
    except Exception:
        return False

    avg = sum(volumes[:-3]) / max(len(volumes[:-3]), 1)

    return volumes[-1] > avg * 2 and volumes[-2] > avg * 1.2


# ==================================
# 🧠 CONFIDENCE SCORE
# ==================================

def crowd_confidence_score(candles: List[Dict[str, Any]]) -> int:

    score = 0

    if crowd_engine_ok(candles):
        score += 1
    if crowd_wave_v2(candles):
        score += 1
    if second_wave_detect(candles):
        score += 1
    if crowd_pressure_build(candles):
        score += 1
    if early_momentum_shift(candles):
        score += 1
    if liquidity_compression(candles):
        score += 1

    return score


# ==================================
# 🧾 ОБЪЯСНЕНИЕ СИГНАЛА (РУССКИЙ)
# ==================================

def crowd_engine_explain(candles: List[Dict[str, Any]]) -> str:

    reasons = []

    if crowd_engine_ok(candles):
        reasons.append("🧠 Толпа начала активно входить (объём + ускорение)")
    if crowd_wave_v2(candles):
        reasons.append("🚀 Обнаружена вторая волна входа")
    if second_wave_detect(candles):
        reasons.append("⚡ Быстрая вторая волна объёма")
    if crowd_pressure_build(candles):
        reasons.append("💥 Объём растёт каждую свечу — давление покупателей")
    if early_momentum_shift(candles):
        reasons.append("⚡ Раннее ускорение рынка")
    if liquidity_compression(candles):
        reasons.append("🧨 Сжатие диапазона — возможный выстрел")

    if not reasons:
        return "Толпа пока не подтверждена"

    return "\n".join(reasons)


# ==================================
# 🔥 FINAL SIGNAL
# ==================================

def crowd_engine_signal(candles: List[Dict[str, Any]]) -> bool:

    try:
        if not smart_silence_filter(candles):
            return False

        score = crowd_confidence_score(candles)

        return score >= 1

    except Exception:
        return False
