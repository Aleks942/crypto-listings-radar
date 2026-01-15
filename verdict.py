# verdict.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class Verdict:
    action: str   # "PLAY" | "WAIT" | "SKIP"
    reason: str

def decide_verdict(score_grade: str, entry_mode: str, has_exit: bool) -> Verdict:
    """
    Правила:
    - C -> SKIP
    - entry_mode == WAIT -> SKIP
    - нет exit -> SKIP
    - A + valid entry + exit -> PLAY
    - B + valid entry + exit -> WAIT
    """
    score_grade = (score_grade or "").upper()
    entry_mode = (entry_mode or "").upper()

    if score_grade == "C":
        return Verdict("SKIP", "Score C (weak setup)")

    if entry_mode in ("WAIT", "", "NO-SETUP", "NO_SETUP"):
        return Verdict("SKIP", "No clean entry window")

    if not has_exit:
        return Verdict("SKIP", "No exit plan (risk not controllable)")

    if score_grade == "A":
        return Verdict("PLAY", "Score A + valid entry + exit plan ready")

    if score_grade == "B":
        return Verdict("WAIT", "Score B (needs confirmation / safer trigger)")

    return Verdict("SKIP", "Unknown grade / safety fallback")
