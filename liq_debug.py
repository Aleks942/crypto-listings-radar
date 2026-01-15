import time
from typing import Dict, Any


def should_send_liq_debug(state: Dict[str, Any], cid: int, every_sec: int = 3600) -> bool:
    state.setdefault("liq_debug", {})
    rec = state["liq_debug"].get(str(int(cid)))
    if not rec:
        return True
    last_ts = float(rec.get("ts") or 0)
    return (time.time() - last_ts) >= float(every_sec)


def mark_liq_debug_sent(state: Dict[str, Any], cid: int) -> None:
    state.setdefault("liq_debug", {})
    state["liq_debug"][str(int(cid))] = {"ts": time.time()}


def build_liq_debug_text(symbol: str, liq: Dict[str, Any]) -> str:
    spread = liq.get("spread_pct")
    n5 = float(liq.get("notional_5m") or 0)
    n15 = float(liq.get("notional_15m") or 0)
    reason = liq.get("reason") or "BLOCK"
    market = liq.get("market") or "UNKNOWN"

    spread_s = "n/a" if spread is None else f"{float(spread):.2f}%"
    return (
        "🧯 <b>LIQUIDITY GATE</b> (DEBUG)\n\n"
        f"<b>{symbol}</b>\n"
        f"Market: <b>{market}</b>\n"
        f"Spread: <b>{spread_s}</b>\n"
        f"Notional: 5m=<b>${n5:,.0f}</b> | 15m=<b>${n15:,.0f}</b>\n"
        f"Причина: {reason}"
    )
