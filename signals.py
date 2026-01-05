# signals.py

from datetime import datetime, timezone
from config_signals import (
    CONFIRM_MIN_AGE_MIN,
    CONFIRM_MAX_AGE_MIN,
    CONFIRM_VOLUME_MULTIPLIER,
    CONFIRM_PRICE_DROP_MAX,
    CONFIRM_MIN_VOLUME_USD
)

def minutes_since(ts_iso: str) -> float:
    ts = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return (now - ts).total_seconds() / 60


def check_confirm(token, baseline):
    """
    token    — текущие данные из CMC
    baseline — сохранённые стартовые данные
    """

    age_min = minutes_since(token["date_added"])

    # 1. Проверка времени
    if age_min < CONFIRM_MIN_AGE_MIN or age_min > CONFIRM_MAX_AGE_MIN:
        return None

    # 2. Минимальный объём
    vol_now = token["volume_24h"]
    if vol_now < CONFIRM_MIN_VOLUME_USD:
        return None

    # 3. Рост объёма
    vol_base = baseline["volume_24h"]
    if vol_base <= 0:
        return None

    volume_multiplier = vol_now / vol_base
    if volume_multiplier < CONFIRM_VOLUME_MULTIPLIER:
        return None

    # 4. Цена не валится
    price_now = token["price"]
    price_base = baseline["price"]

    if price_base > 0:
        price_change = (price_now - price_base) / price_base
        if price_change < CONFIRM_PRICE_DROP_MAX:
            return None

    # ✅ CONFIRM ПРОЙДЕН
    return {
        "type": "CONFIRM",
        "volume_x": round(volume_multiplier, 2),
        "price_change_pct": round(price_change * 100, 2),
        "age_min": int(age_min)
    }

