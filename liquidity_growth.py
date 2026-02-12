# liquidity_growth.py

def liquidity_growth_ok(candles):

    if not candles or len(candles) < 12:
        return False

    try:
        closes = [float(c[4]) for c in candles[-12:]]
        volumes = [float(c[5]) for c in candles[-12:]]
    except Exception:
        return False

    # цена должна быть восходящей мягко
    up_moves = 0
    for i in range(1, len(closes)):
        if closes[i] >= closes[i-1]:
            up_moves += 1

    # объём должен увеличиваться
    v_first = sum(volumes[:6])
    v_last = sum(volumes[6:])

    price_ok = up_moves >= 7
    volume_ok = v_last > v_first * 1.2

    return price_ok and volume_ok
