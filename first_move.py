from typing import List, Dict, Any

from score_engine import Candle, score_market


def build_first_move_signal(
    symbol: str,
    candles_raw: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    FIRST MOVE + SCORE
    """

    # --- преобразуем свечи ---
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

    # --- считаем SCORE ---
    score = score_market(candles)

    # --- фильтр ---
    if score.letter == "C":
        return {
            "ok": False,
            "reason": f"SCORE {score.letter} — {score.reason}",
        }

    # --- базовые условия FIRST MOVE ---
    last = candles[-1]
    prev = candles[-2]

    impulse_ok = (last.h - last.l) >= 1.2 * (prev.h - prev.l)
    close_strong = last.c > (last.l + 0.5 * (last.h - last.l))

    if not (impulse_ok and close_strong):
        return {
            "ok": False,
            "reason": "Нет импульса или слабое закрытие",
        }

    # --- SUCCESS ---
    text = (
        f"🟢 FIRST MOVE — ENTRY OPEN\n\n"
        f"<b>{symbol}</b>\n"
        f"SCORE: {score.letter} ({score.points}/4)\n\n"
        f"Причина:\n"
        f"• {score.reason}\n\n"
        f"Риск:\n"
        f"• 0.25% депо\n\n"
        f"Exit:\n"
        f"• TP1 +1R → 50%\n"
        f"• Стоп в BE"
    )

    return {
        "ok": True,
        "score": score.letter,
        "text": text,
    }
