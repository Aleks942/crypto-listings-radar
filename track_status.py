from typing import Optional


def build_track_status_text(
    name: str,
    symbol: str,
    age_days: Optional[float],
    mcap: float,
    vol: float,
    binance_ok: bool,
    bybit_spot_ok: bool,
    bybit_linear_ok: bool,
) -> str:
    age_txt = "?" if age_days is None else str(age_days)

    def yn(x: bool) -> str:
        return "✅" if x else "❌"

    where = []
    if binance_ok:
        where.append("Binance")
    if bybit_spot_ok:
        where.append("Bybit spot")
    if bybit_linear_ok:
        where.append("Bybit perp (linear)")
    where_txt = ", ".join(where) if where else "пока нигде (на Binance/Bybit)"

    # Почему нет FIRST MOVE
    if not (binance_ok or bybit_spot_ok or bybit_linear_ok):
        reason = (
            "Торги ещё не появились на Binance/Bybit. "
            "Чаще всего токен пока торгуется на DEX или на другой CEX."
        )
        next_step = "Бот продолжит ждать и проверять по расписанию."
    else:
        reason = (
            "Торги уже есть, но FIRST MOVE появится только когда будут свечи и SCORE пройдёт фильтр."
        )
        next_step = "Следующий сигнал будет FIRST MOVE / CONFIRM-LIGHT, если рынок даст сетап."

    text = (
        "🛰 <b>TRACK STATUS</b>\n\n"
        f"<b>{name}</b> ({symbol})\n"
        f"Возраст: {age_txt} дн\n"
        f"Market Cap: ${mcap:,.0f}\n"
        f"Volume 24h: ${vol:,.0f}\n\n"
        "Проверка торгов:\n"
        f"• Binance: {yn(binance_ok)}\n"
        f"• Bybit spot: {yn(bybit_spot_ok)}\n"
        f"• Bybit perp (linear): {yn(bybit_linear_ok)}\n\n"
        f"Где сейчас: <b>{where_txt}</b>\n\n"
        f"Почему тишина:\n• {reason}\n\n"
        f"Дальше:\n• {next_step}"
    )
    return text
