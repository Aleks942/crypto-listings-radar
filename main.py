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
)

from detect_trading import (
    check_binance,
    check_bybit,
    bybit_symbol_exists,
    binance_symbol_exists,
)

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

from track_status import build_track_status_text


# ==================================================
# ENV knobs
# ==================================================
TRACK_TTL_HOURS = int(os.getenv("TRACK_TTL_HOURS", "24").strip() or "24")
ALLOW_UNVERIFIED_TRACK = os.getenv("ALLOW_UNVERIFIED_TRACK", "0").strip() == "1"
DEBUG = os.getenv("DEBUG", "OFF").strip().upper() == "ON"

# раз в сколько минут писать TRACK STATUS по одному токену (чтобы не спамить)
TRACK_STATUS_COOLDOWN_MIN = int(os.getenv("TRACK_STATUS_COOLDOWN_MIN", "360").strip() or "360")  # 6 часов


# ==================================================
# helpers
# ==================================================
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
        except Exception as e:
            # любые редкие ошибки Telegram — тоже ретраим
            last_err = e
            await asyncio.sleep(1.5)
    raise last_err


def cleanup_tracked_ttl(state: dict) -> int:
    ttl_sec = max(1, TRACK_TTL_HOURS) * 3600
    now = time.time()

    tracked = set(state.get("tracked", []))
    meta = state.get("tracked_meta", {}) or {}

    removed = 0
    keep = []
    for cid in tracked:
        key = str(cid)
        ts = float((meta.get(key) or {}).get("ts", 0.0) or 0.0)
        if ts <= 0 or (now - ts) >= ttl_sec:
            removed += 1
            meta.pop(key, None)
        else:
            keep.append(int(cid))

    if removed > 0:
        state["tracked"] = sorted(keep)
        state["tracked_meta"] = meta

    return removed


def mark_tracked_meta(state: dict, cid: int, symbol: str, name: str):
    meta = state.get("tracked_meta", {}) or {}
    meta[str(cid)] = {"ts": float(time.time()), "symbol": symbol, "name": name}
    state["tracked_meta"] = meta


# ==================================================
# scan
# ==================================================
async def scan_once(app: Application, settings: Settings, cmc: CMCClient, sheets: SheetsClient):
    state = load_state()

    # уборка TTL
    cleanup_tracked_ttl(state)

    seen = seen_ids(state)
    tracked = tracked_ids(state)

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

        # ------------------------------
        # Sheets log
        # ------------------------------
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

        # ------------------------------
        # ULTRA-EARLY -> TRACK
        # ------------------------------
        if age is not None and age <= settings.max_age_days and vol >= settings.min_volume_usd:
            reason = is_unverified_token(symbol, name)

            if reason and not ALLOW_UNVERIFIED_TRACK:
                if cid not in seen:
                    await safe_send(
                        app,
                        settings.chat_id,
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

            if cid not in seen:
                await safe_send(
                    app,
                    settings.chat_id,
                    (
                        "⚡ <b>ULTRA-EARLY</b>\n\n"
                        f"<b>{name}</b> ({symbol})\n"
                        f"Возраст: {age} дн\n"
                        f"Market Cap: ${mcap:,.0f}\n"
                        f"Volume 24h: ${vol:,.0f}\n\n"
                        "👀 Добавлен в TRACK MODE\n"
                        "⏳ Ждём появления торгов"
                    ),
                    parse_mode=ParseMode.HTML,
                )
                mark_seen(state, cid)
                mark_tracked(state, cid)
                mark_tracked_meta(state, cid, symbol, name)
                save_state(state)

        # ------------------------------
        # TRACK -> trading / candles
        # ------------------------------
        if cid not in tracked:
            continue

        # подробная проверка (для TRACK STATUS)
        binance_ok = binance_symbol_exists(symbol)
        bybit_spot_ok = bybit_symbol_exists("spot", symbol)
        bybit_linear_ok = bybit_symbol_exists("linear", symbol)

        trading_any = binance_ok or bybit_spot_ok or bybit_linear_ok

        # ---- TRACK STATUS (если торгов нет) ----
        if not trading_any:
            cooldown_sec = max(1, TRACK_STATUS_COOLDOWN_MIN) * 60
            if track_status_cooldown_ok(state, cid, cooldown_sec):
                text = build_track_status_text(
                    name=name,
                    symbol=symbol,
                    age_days=age,
                    mcap=mcap,
                    vol=vol,
                    binance_ok=binance_ok,
                    bybit_spot_ok=bybit_spot_ok,
                    bybit_linear_ok=bybit_linear_ok,
                )
                await safe_send(app, settings.chat_id, text, parse_mode=ParseMode.HTML)
                mark_track_status_sent(state, cid, time.time())
                save_state(state)
            continue

        # совместимость (старые функции)
        _ = check_binance(symbol)
        _ = check_bybit(symbol)

        # ------------------------------
        # FIRST MOVE (5m)
        # ------------------------------
        candles_5m = []
        # приоритет: Binance -> Bybit (с fallback внутри candles_bybit.py)
        if binance_ok:
            candles_5m = get_binance_5m(symbol)
        else:
            candles_5m = get_bybit_5m(symbol)

        FIRST_COOLDOWN = 60 * 60  # 1 час

        if candles_5m:
            fm = first_move_eval(symbol, candles_5m)
            if (
                fm.get("ok")
                and not first_move_sent(state, cid)
                and first_move_cooldown_ok(state, cid, FIRST_COOLDOWN)
            ):
                await safe_send(app, settings.chat_id, fm["text"], parse_mode=ParseMode.HTML)
                mark_first_move_sent(state, cid, time.time())
                save_state(state)

        # ------------------------------
        # CONFIRM-LIGHT (15m)
        # ------------------------------
        if get_binance_15m is None and get_bybit_15m is None:
            continue

        candles_15m = []
        if binance_ok and get_binance_15m is not None:
            candles_15m = get_binance_15m(symbol)
        elif get_bybit_15m is not None:
            candles_15m = get_bybit_15m(symbol)

        CONFIRM_COOLDOWN = 2 * 60 * 60  # 2 часа

        if candles_15m:
            cl = confirm_light_eval(symbol, candles_15m)
            if (
                cl.get("ok")
                and not confirm_light_sent(state, cid)
                and confirm_light_cooldown_ok(state, cid, CONFIRM_COOLDOWN)
            ):
                await safe_send(app, settings.chat_id, cl["text"], parse_mode=ParseMode.HTML)
                mark_confirm_light_sent(state, cid, time.time())
                save_state(state)

    sheets.flush()
    save_state(state)


# ==================================================
# main loop
# ==================================================
async def main():
    settings = Settings.load()

    app = Application.builder().token(settings.bot_token).build()
    cmc = CMCClient(settings.cmc_api_key)
    sheets = SheetsClient(
        settings.google_sheet_url,
        settings.google_service_account_json,
        settings.sheet_tab_name,
    )

    await app.initialize()
    await app.start()

    # STARTUP GUARD (фикс порядка: сначала сохраняем, потом шлём)
    state = load_state()
    if not startup_sent_recent(state, cooldown_sec=3600):
        mark_startup_sent(state)
        save_state(state)

        await safe_send(
            app,
            settings.chat_id,
            (
                "📡 Listings Radar запущен\n"
                "Цепочка: ULTRA → TRACK → FIRST MOVE → CONFIRM-LIGHT\n"
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

