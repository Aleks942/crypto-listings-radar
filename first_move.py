from typing import List, Dict, Any

from score_engine import Candle, score_market
from entry_window import build_entry_plan
from exit_plan import build_exit_plan
from verdict import decide_verdict
from summary_mode import build_summary_message


def first_move_eval(
    symbol: str,
    candles_raw: List[Dict[str, Any]],
    market: str,
) -> Dict[str, Any]:
    """
    FIRST MOVE (5m)
    SCORE → базовый импульс → ENTRY → EXIT → VERDICT → SUMMARY
    """

    if not candles_raw or len(candles_raw) < 3:
        return {"ok": False, "reason": "Недостаточно свечей"}

    # SCORE candles (твоя структура o/h/l/c/v)
    candles = [
        Candle(o=c["o"], h=c["h"], l=c["l"], c=c["c"], v=c["v"])
        for c in candles_raw
    ]

    score = score_market(candles)
    if score.letter == "C":
        return {"ok": False, "reason": f"SCORE C — {score.reason}"}

    # базовый фильтр импульса
    last = candles[-1]
    prev = candles[-2]

    impulse_ok = (last.h - last.l) >= 1.2 * (prev.h - prev.l)
    close_strong = last.c > (last.l + 0.5 * (last.h - last.l))

    if not impulse_ok:
        return {"ok": False, "reason": "Нет импульса"}
    if not close_strong:
        return {"ok": False, "reason": "Слабое закрытие"}

    # адаптер под entry_window (open/high/low/close/volume)
    candles_for_plan = [
        {"open": c["o"], "high": c["h"], "low": c["l"], "close": c["c"], "volume": c["v"]}
        for c in candles_raw
    ]

    plan = build_entry_plan(candles_for_plan, tf="5m")
    exitp = build_exit_plan(entry=plan.entry, stop=plan.stop, score_grade=score.letter, tf="5m")
    ver = decide_verdict(score_grade=score.letter, entry_mode=plan.mode, has_exit=(exitp.tp1 is not None))

    if ver.action == "SKIP":
        return {"ok": False, "reason": ver.reason}

    score_details = [score.reason] if getattr(score, "reason", None) else []
    risk_note = "EARLY / AGGRESSIVE. Новый листинг — высокая волатильность."
    if score.letter == "A" and plan.mode == "PULLBACK":
        risk_note = "A-grade + pullback. Вход более контролируемый, но риск обязателен."

    text = build_summary_message(
        token=symbol,
        market=market,
        stage="FIRST MOVE",
        tf="5m",
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
