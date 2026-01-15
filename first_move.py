from typing import List, Dict, Any

from score_engine import Candle, score_market
from entry_window import build_entry_plan


def first_move_eval(symbol: str, candles_raw: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    FIRST MOVE (5m)
    - SCORE engine A/B/C
    - ENTRY WINDOW: BREAKOUT / PULLBACK / WAIT
    - Возвращает {"ok": True, "text": "..."} или {"ok": False, "reason": "..."}
    """

    # --- нормализуем свечи в формат score_engine ---
    candles = [
        Candle(
            o=float(c.get("o", 0)),
            h=float(c.get("h", 0)),
            l=float(c.get("l", 0)),
            c=float(c.get("c", 0)),
            v=float(c.get("v", 0)),
        )
        for c in candles_raw
        if c is not None
    ]

    if len(candles) < 20:
        return {"ok": False, "reason": "Недостаточно свечей для FIRST MOVE (нужно ≥ 20)"}

    # --- SCORE ---
    score = score_market(candles)
    if score.letter == "C":
        return {"ok": False, "reason": f"SCORE C — {score.reason}"}

    # --- базовая проверка импульса (как у тебя было) ---
    last = candles[-1]
    prev = candles[-2]

    last_range = max(last.h - last.l, 0.0)
    prev_range = max(prev.h - prev.l, 0.0)

    if prev_range <= 0 or last_range <= 0:
        return {"ok": False, "reason": "Плохие свечи (range=0)"}

    impulse_ok = last_range >= 1.2 * prev_range
    close_strong = last.c > (last.l + 0.5 * last_range)

    if not (impulse_ok and close_strong):
        return {"ok": False, "reason": "Нет импульса или слабое закрытие"}

    # --- ENTRY WINDOW (на исходных словарях o/h/l/c/v) ---
    plan = build_entry_plan(symbol, candles_raw, tf="5m")

    if plan.mode == "WAIT" or plan.entry is None or plan.stop is None:
        return {"ok": False, "reason": "WAIT — нет адекватного окна входа"}

    # --- сообщение ---
    notes_block = ""
    if plan.notes:
        # показываем только коротко, чтобы не спамить
        short_notes = plan.notes[-3:] if len(plan.notes) > 3 else plan.notes
        notes_block = "\n".join([f"• {n}" for n in short_notes])

    tp_block = ""
    if plan.tp1 is not None and plan.tp2 is not None:
        tp_block = (
            f"TP1: <b>{plan.tp1}</b> (+1R)\n"
            f"TP2: <b>{plan.tp2}</b> (+2R)\n\n"
            f"Exit:\n"
            f"• TP1 → 50% фиксация\n"
            f"• Стоп в BE\n"
        )
    else:
        tp_block = "Exit:\n• TP1 +1R → 50%\n• Стоп в BE\n"

    text = (
        f"🟢 <b>FIRST MOVE</b> — ENTRY WINDOW\n\n"
        f"<b>{symbol}</b>\n"
        f"SCORE: {score.letter} ({score.points}/4)\n"
        f"Режим: <b>{plan.mode}</b>\n\n"
        f"Entry: <b>{plan.entry}</b>\n"
        f"Stop: <b>{plan.stop}</b>\n"
        f"Invalidation: <b>{plan.invalidation}</b>\n\n"
        f"{tp_block}\n"
        f"Причины:\n"
        f"• {score.reason}\n"
        + (f"{notes_block}\n\n" if notes_block else "\n")
        + (
            "Риск:\n"
            "• 0.25% депо (SAFE)\n"
        )
    )

    return {"ok": True, "score": score.letter, "text": text}
