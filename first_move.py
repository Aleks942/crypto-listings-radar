from typing import List, Dict, Any

from score_engine import Candle, score_market
from entry_window import build_entry_plan


# =====================================================
# NORMALIZE CANDLES
# =====================================================
def _to_ohlcv_dict(c: Dict[str, Any]) -> Dict[str, float]:
    """
    Унификация формата свечей.

    Поддержка:
    {o,h,l,c,v}
    {open,high,low,close,volume}
    """

    if "open" in c:
        return {
            "open": float(c["open"]),
            "high": float(c["high"]),
            "low": float(c["low"]),
            "close": float(c["close"]),
            "volume": float(c.get("volume", 0)),
        }

    return {
        "open": float(c["o"]),
        "high": float(c["h"]),
        "low": float(c["l"]),
        "close": float(c["c"]),
        "volume": float(c.get("v", 0)),
    }


# =====================================================
# FIRST MOVE ENGINE (SHARP VERSION)
# =====================================================
def first_move_eval(symbol: str, candles_raw: List[Dict[str, Any]]) -> Dict[str, Any]:

    # --------------------------
    # Базовая защита
    # --------------------------
    if not candles_raw or len(candles_raw) < 6:
        return {"ok": False, "reason": "Недостаточно свечей"}

    # --------------------------
    # Нормализация
    # --------------------------
    ohlcv = [_to_ohlcv_dict(c) for c in candles_raw]

    candles = [
        Candle(
            o=x["open"],
            h=x["high"],
            l=x["low"],
            c=x["close"],
            v=x["volume"],
        )
        for x in ohlcv
    ]

    # =====================================================
    # SCORE ENGINE
    # =====================================================
    score = score_market(candles)

    if score.letter == "C":
        return {"ok": False, "reason": f"SCORE C — {score.reason}"}

    # =====================================================
    # ИМПУЛЬС (УЛУЧШЕННЫЙ)
    # =====================================================
    last = ohlcv[-1]
    prev = ohlcv[-2]

    last_range = max(0.0, last["high"] - last["low"])
    prev_range = max(1e-12, prev["high"] - prev["low"])

    impulse_ok = last_range >= 1.2 * prev_range
    close_strong = last["close"] > (last["low"] + 0.5 * last_range)

    # 🔥 дополнительный фильтр: объём должен расти
    vol_impulse = last["volume"] >= prev["volume"] * 1.1

    if not (impulse_ok and close_strong and vol_impulse):
        return {"ok": False, "reason": "Нет сильного импульса"}

    # =====================================================
    # ENTRY WINDOW
    # =====================================================
    plan = build_entry_plan(ohlcv, tf="5m")

    if plan.mode == "WAIT":
        return {"ok": False, "reason": "WAIT — окно входа не готово"}

    # =====================================================
    # РУССКИЙ ПЕРЕВОД MODE (как ты просил)
    # =====================================================
    mode_ru = {
        "BREAKOUT": "Пробой уровня — вход на ускорении",
        "PULLBACK": "Откат — вход после возврата цены",
        "CONTINUATION": "Продолжение движения",
    }.get(plan.mode, "Стандартный вход")

    # =====================================================
    # FORMAT MESSAGE
    # =====================================================
    def f(x):
        return "—" if x is None else f"{x:.6f}"

    risk_note = "0.25% депо (консервативный риск)"

    text = (
        "🟢 <b>FIRST MOVE</b> — ENTRY WINDOW\n\n"
        f"<b>{symbol}</b>\n"
        f"SCORE: <b>{score.letter}</b> ({score.points}/4)\n\n"
        "🧠 <b>Почему сигнал</b>:\n"
        f"• {score.reason}\n"
        "• Импульс x1.2+ + рост объёма\n"
        "• Сильное закрытие свечи\n\n"
        "🎯 <b>План входа</b>:\n"
        f"• Mode: <b>{plan.mode}</b>\n"
        f"• Что это значит: {mode_ru}\n"
        f"• Entry: <b>{f(plan.entry)}</b>\n"
        f"• Stop: <b>{f(plan.stop)}</b>\n"
        f"• Invalidation: <b>{f(plan.invalidation)}</b>\n\n"
        "⚠️ <b>Действие</b>:\n"
        "• Толпа начинает входить — готовность к импульсу\n"
        "• Вход только по плану, не по эмоциям\n\n"
        "💰 <b>Риск</b>:\n"
        f"• {risk_note}\n\n"
        "📌 <b>Exit база</b>:\n"
        "• TP1 = +1R → фикс 50%\n"
        "• Остаток → BE\n"
    )

    return {
        "ok": True,
        "score": score.letter,
        "text": text,
        "plan_mode": plan.mode,
    }
