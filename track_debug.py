import time
from typing import Dict, Any, Optional


def should_send_track_debug(state: Dict[str, Any], cid: int, every_sec: int = 3600) -> bool:
    """
    Чтобы не спамить: 1 раз в every_sec на токен.
    """
    state.setdefault("track_debug", {})
    rec = state["track_debug"].get(str(int(cid)))
    if not rec:
        return True
    last_ts = float(rec.get("ts") or 0)
    return (time.time() - last_ts) >= float(every_sec)


def mark_track_debug_sent(state: Dict[str, Any], cid: int) -> None:
    state.setdefault("track_debug", {})
    state["track_debug"][str(int(cid))] = {"ts": time.time()}


def build_track_debug_text(
    symbol: str,
    binance_ok: bool,
    bybit_ok: bool,
    candles_5m_len: int,
    candles_15m_len: int,
    reason: Optional[str] = None,
) -> str:
    market = "NONE"
    if binance_ok:
        market = "BINANCE"
    elif bybit_ok:
        market = "BYBIT"

    lines = [
        "🧪 <b>TRACK DEBUG</b>",
        f"<b>{symbol}</b>",
        "",
        f"Market: <b>{market}</b>",
        f"Candles 5m: <b>{candles_5m_len}</b>",
        f"Candles 15m: <b>{candles_15m_len}</b>",
    ]
    if reason:
        lines += ["", f"Причина: {reason}"]

    lines += [
        "",
        "Что это значит:",
        "• Market=NONE → токена ещё нет на Binance/Bybit",
        "• Candles=0 → API не отдаёт свечи (символ/категория/рынок)",
    ]
    return "\n".join(lines)
