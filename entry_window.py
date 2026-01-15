from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass(frozen=True)
class EntryPlan:
    mode: str                 # "BREAKOUT" | "PULLBACK" | "WAIT"
    entry: Optional[float]
    stop: Optional[float]
    invalidation: Optional[float]
    tp1: Optional[float]
    tp2: Optional[float]
    notes: List[str]


def _f(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def _atr_ohlcv(candles: List[Dict[str, Any]], n: int = 14) -> float:
    """
    ATR по свечам формата проекта: {"o","h","l","c","v"}
    """
    if not candles or len(candles) < 2:
        return 0.0

    trs = []
    start = max(1, len(candles) - n)
    for i in range(start, len(candles)):
        hi = _f(candles[i].get("h"))
        lo = _f(candles[i].get("l"))
        prev_close = _f(candles[i - 1].get("c"))
        tr = max(hi - lo, abs(hi - prev_close), abs(lo - prev_close))
        trs.append(tr)

    return sum(trs) / max(1, len(trs))


def _round_px(x: float) -> float:
    # универсальное округление без тик-сайза
    if x >= 1000:
        return round(x, 2)
    if x >= 1:
        return round(x, 6)
    return round(x, 10)


def build_entry_plan(symbol: str, candles: List[Dict[str, Any]], tf: str = "5m") -> EntryPlan:
    """
    ENTRY WINDOW
    Работает на формате свечей проекта: {"o","h","l","c","v"}.
    Возвращает BREAKOUT / PULLBACK / WAIT + entry/stop/invalidation + TP1/TP2 по R.
    """

    notes: List[str] = []

    if not candles or len(candles) < 20:
        return EntryPlan(
            mode="WAIT",
            entry=None,
            stop=None,
            invalidation=None,
            tp1=None,
            tp2=None,
            notes=["Недостаточно свечей для ENTRY (нужно ≥ 20)"],
        )

    last = candles[-1]
    last_close = _f(last.get("c"))

    # Настройки под TF
    if tf == "5m":
        lookback = 8
        atr_mult_stop = 1.2
        breakout_buf_pct = 0.002  # +0.2%
    else:
        lookback = 10
        atr_mult_stop = 1.0
        breakout_buf_pct = 0.002

    window = candles[-lookback:]
    range_high = max(_f(c.get("h")) for c in window)
    range_low = min(_f(c.get("l")) for c in window)
    swing = max(range_high - range_low, 0.0)

    atr = _atr_ohlcv(candles, n=14)
    if atr <= 0:
        atr = swing * 0.15  # fallback

    # буфер: часть ATR или % swing — защита от шума
    buf = max(atr * 0.25, swing * 0.05)

    notes.append(f"{symbol} TF={tf}")
    notes.append(f"range_high={range_high:.6f}, range_low={range_low:.6f}, swing={swing:.6f}")
    notes.append(f"ATR≈{atr:.6f}, buf≈{buf:.6f}")

    # Базовый стоп и invalidation: ниже range_low с буфером
    base_stop = range_low - buf
    invalidation = range_low - buf

    # 1) BREAKOUT окно — когда цена близко к верху диапазона
    breakout_trigger = range_high * (1.0 + breakout_buf_pct)
    if last_close >= (range_high * 0.995):  # близко к high
        entry = breakout_trigger
        stop = min(base_stop, entry - atr_mult_stop * atr)

        risk = max(entry - stop, 0.0)
        tp1 = entry + 1.0 * risk
        tp2 = entry + 2.0 * risk

        notes.append("ENTRY MODE: BREAKOUT window open")
        notes.append(f"trigger≈{breakout_trigger:.6f} (+0.2% над range_high)")

        return EntryPlan(
            mode="BREAKOUT",
            entry=_round_px(entry),
            stop=_round_px(stop),
            invalidation=_round_px(invalidation),
            tp1=_round_px(tp1),
            tp2=_round_px(tp2),
            notes=notes,
        )

    # 2) PULLBACK окно — вход около 50% swing, если цена выше уровня (откат возможен)
    if swing > 0:
        pullback_entry = range_low + 0.50 * swing

        if last_close > pullback_entry:
            entry = pullback_entry
            stop = min(base_stop, entry - atr_mult_stop * atr)

            risk = max(entry - stop, 0.0)
            tp1 = entry + 1.0 * risk
            tp2 = entry + 2.0 * risk

            notes.append("ENTRY MODE: PULLBACK window open")
            notes.append("entry≈50% retrace (swing)")

            return EntryPlan(
                mode="PULLBACK",
                entry=_round_px(entry),
                stop=_round_px(stop),
                invalidation=_round_px(invalidation),
                tp1=_round_px(tp1),
                tp2=_round_px(tp2),
                notes=notes,
            )

    # 3) WAIT
    notes.append("ENTRY MODE: WAIT (нет адекватного окна входа)")
    return EntryPlan(
        mode="WAIT",
        entry=None,
        stop=None,
        invalidation=None,
        tp1=None,
        tp2=None,
        notes=notes,
    )
