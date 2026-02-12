# liquidity_memory.py

def liquidity_memory_ok(candles):
    """
    Простая логика:
    ищем повторяющиеся зоны объёма.
    """

    if not candles or len(candles) < 20:
        return False

    try:
        volumes = [float(c[5]) for c in candles]
        closes = [float(c[4]) for c in candles]
    except Exception:
        return False

    avg_vol = sum(volumes) / len(volumes)
    if avg_vol <= 0:
        return False

    # ищем 2+ свечи с повышенным объёмом
    high_vol_count = sum(1 for v in volumes if v > avg_vol * 1.6)

    # если крупные входы повторялись — это "память ликвидности"
    if high_vol_count >= 2:
        return True

    return False
