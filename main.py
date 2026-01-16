import asyncio
import os
import time
from telegram.constants import ParseMode
from telegram.ext import Application

from config import Settings
from cmc import CMCClient, age_days
from sheets import SheetsClient, now_iso_utc

from state import (
    load_state,
    save_state,
    seen_ids,
    mark_seen,
    tracked_ids,
    mark_tracked,
    first_move_sent,
    mark_first_move_sent,
    first_move_cooldown_ok,
    confirm_light_sent,
    mark_confirm_light_sent,
    confirm_light_cooldown_ok,
    startup_sent_recent,
    mark_startup_sent,
    track_status_sent,
    mark_track_status_sent,
    track_status_cooldown_ok,
    watch_ids,
    mark_watch,
    unwatch,
    mark_watch_meta,
)

from detect_trading import check_binance, check_bybit, check_bybit_linear
from first_move import first_move_eval
from confirm_light import confirm_light_eval

from candles_binance import get_candles_5m as get_binance_5m
from candles_bybit import get_candles_5m as get_bybit_5m

try:
    from candles_binance import get_candles_15m as get_binance_15m
except Exception:
    get_binance_15m = None

try:
    from candles_bybit import get_candles_15m as get_bybit_15m
except Exception:
    get_bybit_15m = None


TRACK_TTL_HOURS = int((os.getenv("TRACK_TTL_HOURS", "24") or "24").strip() or "24")
ALLOW_UNVERIFIED_TRACK = (os.getenv("ALLOW_UNVERIFIED_TRACK", "0").strip() == "1")
DEBUG = (os.getenv("DEBUG", "OFF").strip().upper() == "ON")

TRACK_STATUS_COOLDOWN_SEC = int((os.getenv("TRACK_STATUS_COOLDOWN_MIN", "120") or "120").strip() or "120") * 60


def is_unverified_token(symbol: str, name: str) -> str | None:
    s = (symbol or "").strip()
    n = (name or "").strip()
    nl = n.lower()

    if "_" in s:
        return "Подозрительный symbol (есть _)"

    url_marks = ["http://", "https://", "www.", ".com", ".io", ".net", ".org", ".xyz"]
    if any(m in nl for m in url_marks):
        return "В названии признаки URL/домена"

    if "." in n:
        return "В названии/описании признаки домена/URL"

    return None


async def safe_send(app: Application, chat_id: str, text: str, parse_mode=ParseMode.HTML, retries: int = 3):
    last_err = None
    for _ in range(retries):
        try:
            return await app.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            last_err = e
            await asyncio.sleep(1.5)
    raise last_err


def _has_candles(candles: list | None) -> bool:
    return bool(candles) and len(candles) >= 20


def build_track_status_text(symbol: str, name: str, binance_ok: bool, bybit_spot_ok: bool, bybit_perp_ok: bool) -> str:
    lines = []
    lines.append("🛰 <b>TRACK STATUS</b>")
    lines.append("")
    lines.append(f"<b>{name}</b> ({symbol})")
    lines.append("")
    lines.append("Проверка торгов:")
    lines.append(f"• Binance: {'✅' if binance_ok else '❌'}")
    lines.append(f"• Bybit spot: {'✅' if bybit_spot_ok else '❌'}")
    lines.append(f"• Bybit perp (linear): {'✅' if bybit_perp_ok else '❌'}")
    lines.append("")
    if not (binance_ok or bybit_spot_ok or bybit_perp_ok):
        lines.append("Где сейчас: пока нигде (на Binance/Bybit)")
        lines.append("")
        lines.append("Почему тишина:")
        lines.append("• Торги ещё не появились на Binance/Bybit. Чаще всего токен пока торгуется на DEX или на другой CEX.")
    else:
        where = []
        if binance_ok:
            where.append("Binance")
        if bybit_spot_ok:
            where.append("Bybit spot")
        if bybit_perp_ok:
            where.append("Bybit perp (linear)")
        lines.append(f"Где сейчас: {', '.join(where)}")
        lines.append("")
        lines.append("Дальше:")
        lines.append("• Включаю сбор свечей → FIRST MOVE (5m) → CONFIRM (15m)")
    return "\n".join(lines)


async def scan_once(app: Application, settings: Settings, cmc: CMCClient, sheets: SheetsClient):
    state = load_state()

    seen = seen_ids(state)
    tracked = tracked_ids(state)
    watch = watch_ids(state)

    coins = cmc.fetch_recent_listings(limit=settings.limit)

    for coin in coins:
        cid = int(coin.get("id") or 0)
        if not cid:
            continue

        usd = (coin.get("quote") or {}).get("USD") or {}
        vol = float(usd.get("volume_24h") or 0)
        mcap = float(usd.get("market_cap") or 0)
        age = age_days(coin.get("date_added"))

        symbol = (coin.get("symbol") or "").strip()
        name = (coin.get("name") or "").strip()
        slug = (coin.get("slug") or "").strip()

        sheets.buffer_append({
            "detected_at": now_iso_utc(),
            "cmc_id": cid,
            "symbol": symbol,
            "name": name,
            "slug": slug,
            "age_days": age,
            "market_cap_usd": mcap,
            "volume24h_usd": vol,
            "status": "NEW",
            "comment": "",
        })

        if age is None:
            continue

        # ULTRA фильтр
        if age <= settings.max_age_days and vol >= settings.min_volume_usd:
            reason = is_unverified_token(symbol, name)
            if reason and not ALLOW_UNVERIFIED_TRACK:
                if cid not in seen:
                    await safe_send(
                        app, settings.chat_id,
                        (
                            "🟡 <b>ULTRA-EARLY (UNVERIFIED)</b>\n\n"
                            f"<b>{name}</b> ({symbol})\n"
                            f"Возраст: {age} дн\n"
                            f"Market Cap: ${mcap:,.0f}\n"
                            f"Volume 24h: ${vol:,.0f}\n\n"
                            f"Причина: {reason}\n\n"
                            "⛔ По умолчанию не трекаю. Если хочешь трекать — поставь <b>ALLOW_UNVERIFIED_TRACK=1</b>"
                        ),
                        parse_mode=ParseMode.HTML,
                    )
                    mark_seen(state, cid)
                    save_state(state)
                continue

            # ULTRA сообщение — один раз
            if cid not in seen:
                await safe_send(
                    app, settings.chat_id,
                    (
                        "⚡ <b>ULTRA-EARLY</b>\n\n"
                        f"<b>{name}</b> ({symbol})\n"
                        f"Возраст: {age} дн\n"
                        f"Market Cap: ${mcap:,.0f}\n"
                        f"Volume 24h: ${vol:,.0f}\n\n"
                        "👀 Добавлен в WATCH MODE\n"
                        "⏳ Ждём появления торгов на Binance/Bybit"
                    ),
                    parse_mode=ParseMode.HTML,
                )
                mark_seen(state, cid)
                mark_watch(state, cid)
                mark_watch_meta(state, cid, symbol, name)
                save_state(state)

        # WATCH → проверка торгов
        if cid in watch and cid not in tracked:
            binance_ok = check_binance(symbol)
            bybit_spot_ok = check_bybit(symbol)
            bybit_perp_ok = check_bybit_linear(symbol)

            # если торгов всё ещё нет — просто пропускаем
            if not (binance_ok or bybit_spot_ok or bybit_perp_ok):
                continue

            # появились торги → переводим в TRACK
            await safe_send(
                app, settings.chat_id,
                (
                    "✅ <b>TRADING FOUND</b>\n\n"
                    f"<b>{name}</b> ({symbol})\n\n"
                    "Перевожу в TRACK MODE и начинаю анализ свечей."
                ),
                parse_mode=ParseMode.HTML,
            )
            unwatch(state, cid)
            mark_tracked(state, cid)
            save_state(state)

        # TRACK → статус + свечи + сигналы
        if cid not in tracked:
            continue

        binance_ok = check_binance(symbol)
        bybit_spot_ok = check_bybit(symbol)
        bybit_perp_ok = check_bybit_linear(symbol)

        # TRACK STATUS (редко)
        if (not track_status_sent(state, cid)) or track_status_cooldown_ok(state, cid, TRACK_STATUS_COOLDOWN_SEC):
            await safe_send(
                app, settings.chat_id,
                build_track_status_text(symbol, name, binance_ok, bybit_spot_ok, bybit_perp_ok),
                parse_mode=ParseMode.HTML,
            )
            mark_track_status_sent(state, cid, time.time())
            save_state(state)

        # свечи 5m: приоритет Binance → Bybit spot → Bybit perp
        candles_5m = []
        if binance_ok:
            candles_5m = get_binance_5m(symbol)
        elif bybit_spot_ok:
            candles_5m = get_bybit_5m(symbol)
        elif bybit_perp_ok:
            candles_5m = get_bybit_5m(symbol)

        FIRST_COOLDOWN = 60 * 60

        if candles_5m:
            fm = first_move_eval(symbol, candles_5m)
            if fm.get("ok") and not first_move_sent(state, cid) and first_move_cooldown_ok(state, cid, FIRST_COOLDOWN):
                await safe_send(app, settings.chat_id, fm["text"], parse_mode=ParseMode.HTML)
                mark_first_move_sent(state, cid, time.time())
                save_state(state)

        # 15m
        if get_binance_15m is None and get_bybit_15m is None:
            continue

        candles_15m = []
        if binance_ok and get_binance_15m is not None:
            candles_15m = get_binance_15m(symbol)
        elif (bybit_spot_ok or bybit_perp_ok) and get_bybit_15m is not None:
            candles_15m = get_bybit_15m(symbol)

        if not candles_15m:
            continue

        CONFIRM_COOLDOWN = 2 * 60 * 60
        cl = confirm_light_eval(symbol, candles_15m)
        if cl.get("ok") and not confirm_light_sent(state, cid) and confirm_light_cooldown_ok(state, cid, CONFIRM_COOLDOWN):
            await safe_send(app, settings.chat_id, cl["text"], parse_mode=ParseMode.HTML)
            mark_confirm_light_sent(state, cid, time.time())
            save_state(state)

    sheets.flush()
    save_state(state)


async def main():
    settings = Settings.load()

    app = Application.builder().token(settings.bot_token).build()
    cmc = CMCClient(settings.cmc_api_key)
    sheets = SheetsClient(settings.google_sheet_url, settings.google_service_account_json, settings.sheet_tab_name)

    await app.initialize()
    await app.start()

    state = load_state()
    if not startup_sent_recent(state, cooldown_sec=3600):
        mark_startup_sent(state)
        save_state(state)
        await safe_send(
            app,
            settings.chat_id,
            (
                "📡 Listings Radar запущен\n"
                "Цепочка: ULTRA → WATCH → (TRADING FOUND) → TRACK → FIRST MOVE → CONFIRM-LIGHT\n"
                "SUMMARY: ENTRY + EXIT + VERDICT\n"
                f"DEBUG: {'ON' if DEBUG else 'OFF'}"
            ),
            parse_mode=ParseMode.HTML,
        )

    while True:
        try:
            await scan_once(app, settings, cmc, sheets)
        except Exception as e:
            try:
                await safe_send(app, settings.chat_id, f"❌ Ошибка: {e}", parse_mode=None)
            except Exception:
                pass
        await asyncio.sleep(settings.check_interval_min * 60)


if __name__ == "__main__":
    asyncio.run(main())

