# decision_engine.py

from dataclasses import dataclass


@dataclass
class DecisionResult:
    score: int
    level: str
    boosted: bool
    reasons: str


def decision_engine(
    *,
    crowd_recent: bool,
    crowd_flow: bool,
    liq_growth: bool,
    liq_memory: bool,
    first_ok: bool,
    anti_scam_ok: bool,
):
    """
    Центральный мозг радара.

    WATCH  = наблюдаем
    GO     = готовим вход
    HUNT   = высокий приоритет (почти institutional уровень)
    """

    if not anti_scam_ok:
        return DecisionResult(0, "WATCH", False, "anti_scam_fail")

    score = 0
    reasons = []
    boosted = False

    # CROWD
    if crowd_recent:
        score += 2
        reasons.append("crowd_recent(+2)")

    if crowd_flow:
        score += 1
        reasons.append("crowd_flow(+1)")

    # LIQUIDITY
    if liq_growth:
        score += 2
        reasons.append("liq_growth(+2)")

    if liq_memory:
        score += 1
        reasons.append("liq_memory(+1)")

    # FIRST MOVE
    if first_ok:
        score += 3
        reasons.append("first_move(+3)")

    # BOOST если толпа + импульс
    if first_ok and crowd_recent:
        score += 1
        boosted = True
        reasons.append("crowd_boost(+1)")

    # Уровни
    if score >= 7:
        level = "HUNT"
    elif score >= 5:
        level = "GO"
    else:
        level = "WATCH"

    return DecisionResult(score, level, boosted, "; ".join(reasons))
