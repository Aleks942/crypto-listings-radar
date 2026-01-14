from score_engine import score_market
from state import mark_spike_sent, spike_sent_ids


def confirm_light_entry(candles, state, cid):
    """
    CONFIRM-LIGHT:
    - только SCORE A
    - антидубликат
    """

    if cid in spike_sent_ids(state):
        return None

    score = score_market(candles)

    if score.letter != "A":
        return None

    mark_spike_sent(state, cid)

    return {
        "score": score,
        "reason": "SCORE A + подтверждение импульса",
    }
