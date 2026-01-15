from typing import List, Dict, Any

from score_engine import Candle, score_market
from entry_window import build_entry_plan
from exit_plan import build_exit_plan
from verdict import decide_verdict
from summary_mode import build_summary_message


def confirm_light_eval(
    symbol: str,
    candles_raw: List[Dict[str, Any]],
    market: str,
) -> Dict[str, Any]:
    """
    CONFIRM-LIGHT (15m)
    Строже, чем FIRST MOVE: нужен более "чистый" сетап.
    """

    if not candles_raw or len(candles_raw) < 6:
        return {"ok": False, "reason": "Недостаточно свечей (15m)"}

    candles = [
        Candle(o=c["o"], h=c["h"], l=c["l"], c=c["c"], v=c["v"])
        for c in candles_raw
    ]

    score = score_market(candles)
    # Confirm строже: пропускаем всё, что не A
    if score.letter != "A":
        return {"ok": False, "reason": f"Confirm wants A-grade (now {score.letter}) — {score.reason}"}

    # Базовая структура (простая): последние 3 свечи не должны ломать лои резко
    last = candles[-1]
    prev = candles[-2]
    prev2 = candles[-3]

    # защита от “пилы”
    structure_ok = (last.l >= min(prev.l, prev2.l)) or (last.c > prev.c)
    if not structure_ok:
        return {"ok": False, "reason": "Структура слабая для CONFIRM"}

    candles_for_plan = [
        {"open": c["o"], "high": c["h"], "low": c["l"], "close": c["c"], "volume": c["v"]}
        for c in candles_raw
    ]

    plan = build_entry_plan(candles_for_plan, tf="15m")
    exitp = build_exit_plan(entry=plan.entry, stop=plan.stop, score_grade=score.letter, tf="15m")
    ver = decide_verdict(score_grade=score.letter, entry_mode=plan.mode, has_exit=(exitp.tp1 is not None))

    if ver.action == "SKIP":
        return {"ok": False, "reason": ver.reason}

    score_details = [score.reason] if getattr(score, "reason", None) else []
    risk_note = "CONFIRM (15m) — safer than 5m, но листинг всё равно волатильный."

    text = build_summary_message(
        token=symbol,
        market=market,
        stage="CONFIRM-LIGHT",
        tf="15m",
        score_grade=score.letter,
        score_details=score_details,
        entry_mode=plan.mode,
        entry=plan.entry,
        stop=plan.stop,
        invalidation=plan.invalidation,
        entry_notes=plan.notes,
        tp1=exitp.tp1,
        tp2=exitp.tp2,
        trail_hint=exitp.trail_hint,
        exit_notes=exitp.notes,
        verdict_action=ver.action,
        verdict_reason=ver.reason,
        risk_note=risk_note,
    )

    return {"ok": True, "score": score.letter, "text": text}
