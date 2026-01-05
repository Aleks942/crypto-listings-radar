# signals.py

from datetime import datetime, timezone
from config_signals import (
    # CONFIRM (жёсткий)
    CONFIRM_MIN_AGE_MIN,
    CONFIRM_MAX_AGE_MIN,
    CONFIRM_VOLUME_MULTIPLIER,
    CONFIRM_PRICE_DROP_MAX,
    CONFIRM_MIN_VOLUME_USD,

    # CONFIRM-LIGHT (ранний)
    CONFIRM_LIGHT_ENABLED,
    CONFIRM_LIGHT_MIN_MINUTES,
    CONFIRM_LIGHT_VOL_MULT,
    CONFIRM_LIGHT_MAX_AGE_DAYS,
)


# ------------------------
# ВСПОМОГАТЕЛЬНОЕ
# ------------------------

def minutes_since(ts_iso: str) -> float:
    ts = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return (now - ts).total_seconds() / 60


# ------------------------
# CONFIRM (ЖЁСТКИЙ)
# ------------------------

def check_confirm(token, baseline):
    """
    token    — текущие данные из CMC
    baseline — стартовые данные (при первом обнаружении)
    """

    age_min = minutes_since(token["date_added"])

    # 1. Время
    if age_min < CONFIRM_MIN_AGE_MIN or age_min > CONFIRM_MAX_AGE_MIN:
        return None

    # 2. Минимальный объём
    vol_now = token["volume_24h"]
    if vol_now < CONFIRM_MIN_VOLUME_USD:
        return None

    # 3. Рост объёма относительно baseline
    vol_base = baseline["volume_24h"]
    if vol_base <= 0:
        return None

    volume_x = vol_now / vol_base
    if volume_x < CONFIRM_VOLUME_MULTIPLIER:
        return None

    # 4. Цена не валится
    price_now = token["price"]
    price_base = baseline["price"]

    price_change_pct = 0.0
    if price_base > 0:
        price_change = (price_now - price_base) / price_base
        if price_change < CONFIRM_PRICE_DROP_MAX:
            return None
        price_change_pct = price_change * 100

    return {
        "type": "CONFIRM",
        "volume_x": round(volume_x, 2),
        "price_change_pct": round(price_change_pct, 2),
        "age_min": int(age_min),
    }


# ------------------------
# CONFIRM-LIGHT (РАННИЙ)
# ------------------------

def check_confirm_light(token, prev_snapshot):
    """
    token        — текущие данные из CMC
    prev_snapshot — данные с ПРЕДЫДУЩЕЙ проверки
    """

    if not CONFIRM_LIGHT_ENABLED:
        return None

    # возраст в минутах
    age_min = minutes_since(token["date_added"])
    age_days = age_min / 1440

    if age_days > CONFIRM_LIGHT_MAX_AGE_DAYS:
        return None

    if not prev_snapshot:
        return None

    # прошло ли достаточно времени
    minutes_passed = (token["ts"] - prev_snapshot["ts"]) / 60
    if minutes_passed < CONFIRM_LIGHT_MIN_MINUTES:
        return None

    vol_prev = prev_snapshot["volume_24h"]
    vol_now = token["volume_24h"]

    if vol_prev <= 0:
        return None

    vol_x = vol_now / vol_prev

    if vol_x < CONFIRM_LIGHT_VOL_MULT:
        return None

    return {
        "type": "CONFIRM_LIGHT",
        "volume_x": round(vol_x, 2),
        "minutes": int(minutes_passed),
        "age_min": int(age_min),
    }
