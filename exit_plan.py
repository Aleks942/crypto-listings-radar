# exit_plan.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class ExitPlan:
    tp1: Optional[float]
    tp2: Optional[float]
    be_after_tp1: bool
    trail_hint: str
    notes: str

def _round(x: float) -> float:
    # достаточно для крипты; если хочешь, сделаем динамическое округление по цене
    return round(float(x), 8)

def build_exit_plan(
    entry: Optional[float],
    stop: Optional[float],
    score_grade: str,   # "A" | "B" | "C"
    tf: str,            # "5m" | "15m"
) -> ExitPlan:
    """
    Математика простая:
    R = entry - stop (для лонга)
    TP1 = entry + 1R
    TP2 = entry + 2R
    Для CONFIRM (15m) можно чуть консервативнее: TP1 = 0.8R (по желанию).
    """
    if entry is None or stop is None:
        return ExitPlan(tp1=None, tp2=None, be_after_tp1=False, trail_hint="", notes="No entry/stop to build exit plan")

    r = entry - stop
    if r <= 0:
        return ExitPlan(tp1=None, tp2=None, be_after_tp1=False, trail_hint="", notes="Invalid R (entry <= stop)")

    # Консервативность (по желанию):
    # для 15m CONFIRM можно быстрее защищаться
    tp1_mult = 1.0
    if tf == "15m" and score_grade == "B":
        tp1_mult = 0.8

    tp1 = entry + r * tp1_mult
    tp2 = entry + r * 2.0

    # trailing подсказка — только текст, без торговли
    trail_hint = "Trail stop under higher lows (move only after candle close)"
    if tf == "15m":
        trail_hint = "Trail stop under 15m higher lows / structure (after close)"

    notes = "TP1 -> partial (30–50%) + move stop to BE; remainder -> TP2 or trail"
    if score_grade == "B":
        notes = "More conservative: take TP1 faster, protect BE early; avoid FOMO"

    return ExitPlan(
        tp1=_round(tp1),
        tp2=_round(tp2),
        be_after_tp1=True,
        trail_hint=trail_hint,
        notes=notes
    )
