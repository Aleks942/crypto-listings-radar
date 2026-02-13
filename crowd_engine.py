# crowd_engine.py

from typing import List, Dict, Any


# ==============================
# 🧠 CROWD ENGINE PRO (текущий)
# ==============================

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


# ==================================
# 🚀 CROWD ENGINE V2 — ВТОРАЯ ВОЛНА
# ==================================

def crowd_wave_v2(candles: List[Dict[str, Any]]) -> bool:
    """
    Ловит вторую волну объёма:
    импульс → откат → повторный вход толпы
    """

    if not candles or len(candles) < 20:
        return False

    try:
        volumes = [float(c[5]) for c in candles]
        closes = [float(c[4]) for c in candles]
    except Exception:
        return False

    avg_vol = sum(volumes[:-5]) / max(len(volumes[:-5]), 1)

    # первый всплеск
    first_spike = max(volumes[-15:-10]) > avg_vol * 2

    # небольшой откат цены
    pullback = closes[-7] < closes[-10]

    # вторая волна объёма
    second_spike = volumes[-1] > avg_vol * 1.8

    return first_spike and pullback and second_spike


# ==================================
# 🔥 ОБЩИЙ ВХОД ДЛЯ MAIN.PY
# ==================================

def crowd_engine_signal(candles: List[Dict[str, Any]]) -> bool:
    """
    Общая точка входа.

    Старый PRO + новый V2.
    Ничего в main.py менять почти не нужно.
    """

    try:
        pro_ok = crowd_engine_ok(candles)
        v2_ok = crowd_wave_v2(candles)

        return pro_ok or v2_ok

    except Exception:
        return False
def second_wave_detect(candles):
    """
    Detect second wave volume expansion.
    """

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

    # первая волна
    first_push = v2 > v1 * 1.6

    # пауза
    pullback = v3 < v2 * 0.8

    # вторая волна
    second_push = v4 > v3 * 1.8

    return first_push and pullback and second_push
