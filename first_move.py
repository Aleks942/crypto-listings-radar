from typing import List, Dict, Any

from score_engine import Candle, score_market
from entry_window import build_entry_plan
from exit_plan import build_exit_plan
from verdict import decide_verdict
from summary_mode import build_summary_message


def build_first_move_signal(
    symbol: str,
    candles_raw: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    FIRST MOVE + SCORE + ENTRY/EXIT/SUMMARY/VERDICT
    """

    # --- преобразуем свечи для SCORE ENGINE ---
    candles = [
        Candle(
            o=c["o"],
            h=c["h"],
            l=c["l"],
            c=c["c"],
            v=c["v"],
        )
        for c in candles_raw
    ]

    # --- свечи для ENTRY/EXIT модулей (адаптер ключей) ---
    candles_for_plan = [
        {
            "open": c["o"],
            "high": c["h"],
            "low":  c["l"],
            "close": c["c"],
            "volume": c["v"],
        }
        for c in candles_raw
    ]

    # --- считаем SCORE ---
    score = score_market(candles)

    # --- фильтр ---
    if score.letter == "C":
        return {"ok": False, "reason": f"SCORE {score.letter} — {score.reason}"}

    # --- базовые условия FIRST MOVE ---
    if len(candles) < 3:
        return {"ok": False, "reason": "Мало свечей для FIRST MOVE"}

    last = candles[-1]
    prev = candles[-2]

    impulse_ok = (last.h - last.l) >= 1.2 * (prev.h - prev.l)
    close_strong = last.c > (last.l + 0.5 * (last.h - last.l))

    if not (impulse_ok and close_strong):
        return {"ok": False, "reason": "Нет импульса или слабое закрытие"}

    # === STEP 4: ENTRY WINDOW ===
    plan = build_entry_plan(candles_for_plan, tf="5m")

    # === STEP 5: EXIT PLAN ===
    exitp = build_exit_plan(
        entry=plan.entry,
        stop=plan.stop,
        score_grade=score.letter,
        tf="5m",
    )

    # === STEP 6.5: VERDICT ===
    ver = decide_verdict(
        score_grade=score.letter,
        entry_mode=plan.mode,
        has_exit=(exitp.tp1 is not None),
    )

    if ver.action == "SKIP":
        return {"ok": False, "reason": ver.reason}

    score_details = [score.reason] if getattr(score, "reason", None) else []
    risk_note = "EARLY / AGGRESSIVE (listing volatile). Follow plan, no FOMO."

    text = build_summary_message(
        token=symbol,
        market="Binance/Bybit",
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
