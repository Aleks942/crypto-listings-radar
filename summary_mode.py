# summary_mode.py
from typing import Optional
from formatting import h, bullet, fmt_price

def build_summary_message(
    token: str,
    market: str,              # "Binance" | "Bybit"
    stage: str,               # "FIRST MOVE" | "CONFIRM-LIGHT"
    tf: str,                  # "5m" | "15m"
    score_grade: str,         # "A" | "B" | "C"
    score_details: list[str], # причины score (короткими буллетами)
    entry_mode: str,          # "BREAKOUT" | "PULLBACK" | "WAIT"
    entry: Optional[float],
    stop: Optional[float],
    invalidation: Optional[float],
    entry_notes: str,
    tp1: Optional[float],
    tp2: Optional[float],
    trail_hint: str,
    exit_notes: str,
    verdict_action: str,      # PLAY | WAIT | SKIP
    verdict_reason: str,
    risk_note: str,
) -> str:
    msg = ""
    msg += f"🧠 <b>NEW LISTING — TRADE SETUP</b>\n\n"
    msg += f"Token: <b>{token}</b>\n"
    msg += f"Market: <b>{market}</b>\n"
    msg += f"Stage: <b>{stage}</b> ({tf})\n"

    msg += h("SCORE")
    msg += f"Grade: <b>{score_grade}</b>\n"
    for r in (score_details or [])[:6]:
        msg += bullet(r)

    msg += h("ENTRY WINDOW")
    msg += f"Mode: <b>{entry_mode}</b>\n"
    msg += f"Entry: <code>{fmt_price(entry)}</code>\n"
    msg += f"Stop: <code>{fmt_price(stop)}</code>\n"
    msg += f"Invalidation: <code>{fmt_price(invalidation)}</code>\n"
    if entry_notes:
        msg += bullet(entry_notes)

    msg += h("EXIT PLAN")
    msg += f"TP1: <code>{fmt_price(tp1)}</code>\n"
    msg += f"TP2: <code>{fmt_price(tp2)}</code>\n"
    if trail_hint:
        msg += bullet(trail_hint)
    if exit_notes:
        msg += bullet(exit_notes)

    msg += h("RISK NOTE")
    msg += bullet(risk_note)

    msg += h("VERDICT")
    tag = "✅" if verdict_action == "PLAY" else ("⏳" if verdict_action == "WAIT" else "❌")
    msg += f"{tag} <b>{verdict_action}</b>\n"
    msg += bullet(verdict_reason)

    return msg

