from dataclasses import dataclass
from typing import List, Dict, Optional


@dataclass
class EntryPlan:
    mode: str                 # "BREAKOUT" | "PULLBACK" | "WAIT"
    entry: Optional[float]
    stop: Optional[float]
    invalidation: Optional[float]
    notes: List[str]


def _atr(candles: List[Dict], n: int = 14) -> float:
    """
    Простой ATR по true range на словарях:
    {open, high, low, close, volume}
    """
    if not candles or len(candles) < 2:
        return 0.0

    trs = []
    start = max(1, len(candles) - n)
    for i in range(start, len(candles)):
        hi = float(candles[i]["high"])
        lo = float(candles[i]["low"])
        prev_close = float(candles[i - 1]["close"])
        tr = max(hi - lo, abs(hi - prev_close), abs(lo - prev_close))
        trs.append(tr)

    return sum(trs) / max(1, len(trs))


def build_entry_plan(candles: List[Dict], tf: str = "5m") -> EntryPlan:
    """
    ENTRY WINDOW (ШАГ 4)
    Даёт понятный план: BREAKOUT / PULLBACK / WAIT
    + entry/stop/invalidation

    Логика:
    - Breakout: пробой high последних N свечей
    - Pullback: откат к середине импульса (50%) или к зоне, но без пробоя лоя
    """

    notes: List[str] = []

    if not candles or len(candles) < 6:
        return EntryPlan(mode="WAIT", entry=None, stop=None, invalidation=None, notes=["Недостаточно свечей для ENTRY"])

    last = candles[-1]
    last_close = float(last["close"])
    last_high = float(last["high"])
    last_low = float(last["low"])

    # Настройки под TF
    if tf == "5m":
        lookback = 8
        atr_mult_stop = 1.2
    else:
        lookback = 10
        atr_mult_stop = 1.0

    # Уровни для breakout
    window = candles[-lookback:]
    range_high = max(float(c["high"]) for c in window)
    range_low = min(float(c["low"]) for c in window)

    atr = _atr(candles, n=14)
    if atr <= 0:
        atr = (range_high - range_low) * 0.15  # fallback

    notes.append(f"TF={tf}, lookback={lookback}")
    notes.append(f"range_high={range_high:.6f}, range_low={range_low:.6f}")
    notes.append(f"ATR≈{atr:.6f}")

    # 1) BREAKOUT — если закрытие рядом с верхом диапазона и есть шанс пробоя
    # Тут мы не ждём факт пробоя (это требует будущей свечи), мы открываем "окно входа".
    breakout_trigger = range_high * 1.002  # +0.2% над high диапазона
    if last_close >= (range_high * 0.995):
        entry = breakout_trigger
        stop = max(range_low, entry - atr_mult_stop * atr)
        invalidation = range_low
        notes.append("ENTRY MODE: BREAKOUT window open")
        notes.append(f"trigger={breakout_trigger:.6f} (≈ +0.2% над диапазоном)")
        return EntryPlan(
            mode="BREAKOUT",
            entry=float(entry),
            stop=float(stop),
            invalidation=float(invalidation),
            notes=notes,
        )

    # 2) PULLBACK — если цена уже улетела, но возможен откат
    # Берём импульсный swing (high-low последних lookback) и даём entry около 50%
    swing = range_high - range_low
    if swing > 0:
        pullback_entry = range_low + 0.50 * swing
        # если цена выше pullback_entry — считаем, что откат возможен
        if last_close > pullback_entry:
            entry = pullback_entry
            stop = max(range_low, entry - atr_mult_stop * atr)
            invalidation = range_low
            notes.append("ENTRY MODE: PULLBACK window open")
            notes.append("entry≈50% swing retrace")
            return EntryPlan(
                mode="PULLBACK",
                entry=float(entry),
                stop=float(stop),
                invalidation=float(invalidation),
                notes=notes,
            )

    # 3) WAIT — если ни то ни другое
    notes.append("ENTRY MODE: WAIT (нет адекватного окна входа)")
    return EntryPlan(mode="WAIT", entry=None, stop=None, invalidation=None, notes=notes)
