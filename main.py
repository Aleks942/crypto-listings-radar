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
)

from detect_trading import check_binance, check_bybit
from first_move import first_move_eval
from confirm_light import confirm_light_eval

from candles_binance import (
    get_candles_5m as get_binance_5m,
    get_candles_15m as get_binance_15m,
)
from candles_bybit import (
    get_candles_5m as get_bybit_5m,
    get_candles_15m as get_bybit_15m,
)

from noise_filter import is_unverified_token, ALLOW_UNVERIFIED_TRACK
from liquidity import liquidity_gate


# =========================
# helpers: safe send / safe flush
# =========================

def _is_broken_pipe(e: Exception) -> bool:
    msg = str(e).lower()
    return ("broken pipe" in msg) or ("errno 32" in msg)


async def safe_send(app, chat_id: str, text: str, *, parse_mode=ParseMode.HTML, silent_on_broken_pipe: bool = False):
    try:
        await app.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
    except Exception as e:
        if silent_on_broken_pipe and _is_broken_pipe(e):
            return
        try:
            await asyncio.sleep(2)
            await app.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
        except Exception:
            return


def safe_sheets_flush(sheets: SheetsClient) -> None:
    try:
        sheets.flush()
    except Exception:
        try:
            time.sleep(2)
            sheets.flush()
        except Exception:
            return


# =========================
# TRACK TTL (auto cleanup)
# =========================

def _track_ttl_seconds() -> int:
    # можно управлять env: TRACK_TTL_HOURS, по умолчанию 24 часа
    hrs = os.getenv("TRACK_TTL_HOURS", "24").strip()
    try:
        h = int(hrs)
    except Exception:
        h = 24
    h = max(1, min(h, 72))  # 1..72
    return h * 3600


async def cleanup_tracked(app, settings, state) -> None:
    """
    Удаляет из TRACK токены, которые висят слишком долго без результата.
    Храним метадату в state["tracked_meta"] = {cid: {ts, symbol, name}}
    """
    ttl_sec = _track_ttl_seconds()
    now = time.time()

    tracked_list = list(state.get("tracked", []))
    if not tracked_list:
        return

    meta = state.setdefault("tracked_meta", {})

    kept = []
    expired = []

    for cid in tracked_list:
        cid_int = int(cid)
        key = str(cid_int)
        m = meta.get(key) or {}

        ts = float(m.get("ts") or 0.0)
        if ts <= 0:
            # если раньше не писали — ставим "сейчас"
            ts = now
            m["ts"] = ts
            meta[key] = m

        if (now - ts) > ttl_sec:
            expired.append((cid_int, m.get("name") or "", m.get("symbol") or f"#{cid_int}"))
        else:
            kept.append(cid_int)

    if expired:
        # аккуратно: отправляем максимум 10 сообщений за один проход
        for cid_int, name, sym in expired[:10]:
            await safe_send(
                app,
                settings.chat_id,
                (
                    "🧹 <b>TRACK EXPIRED</b>\n\n"
                    f"{name} ({sym})\n"
                    f"Причина: нет торгов/сигналов в течение {ttl_sec // 3600}ч\n"
                    "Действие: удалён из TRACK"
                ),
                silent_on_broken_pipe=True,
            )
            meta.pop(str(cid_int), None)

        # если было больше 10 — остальные удалим молча, чтобы не спамить
        for cid_int, _, _ in expired[10:]:
            meta.pop(str(cid_int), None)

        state["tracked"] = sorted(set(kept))
        state["tracked_meta"] = meta


# =========================
# scan loop
# =========================

async def scan_once(app, settings, cmc, sheets):
    state = load_state()

    # 1) перед сканом — чистим TRACK
    await cleanup_tracked(app, settings, state)

    seen = seen_ids(state)
    tracked = tracked_ids(state)

    coins = cmc.fetch_recent_listings(limit=settings.limit)
    now_ts = time.time()

    for coin in coins:
        cid = int(coin.get("id") or 0)
        if not cid:
            continue

        usd = (coin.get("quote") or {}).get("USD") or {}
        vol = float(usd.get("volume_24h") or 0)
        mcap = float(usd.get("market_cap") or 0)
        price = float(usd.get("price") or 0)
        age = age_days(coin.get("date_added"))

        token = {
            "id": cid,
            "symbol": coin.get("symbol"),
            "name": coin.get("name"),
            "slug": coin.get("slug"),
            "date_added": coin.get("date_added"),
            "volume_24h": vol,
            "market_cap": mcap,
            "price": price,
            "ts": now_ts,
        }

        # ------------------------------
        # ULTRA-EARLY conditions (env-driven via Settings)
        # ------------------------------
        ultra_ok = (
            age is not None
            and age <= settings.max_age_days
            and vol >= settings.min_volume_usd
        )

        # ------------------------------
        # ULTRA-EARLY → TRACK MODE (+ UNVERIFIED filter)
        # ------------------------------
        if ultra_ok:
            unverified, reason_uv = is_unverified_token({
                "symbol": token["symbol"],
                "name": token["name"],
                "slug": token["slug"],
                "market_cap": mcap,
                "volume_24h": vol,
            })

            # Sheets log
            sheets.buffer_append({
                "detected_at": now_iso_utc(),
                "cmc_id": cid,
                "symbol": token["symbol"],
                "name": token["name"],
                "slug": token["slug"],
                "age_days": age,
                "market_cap_usd": mcap,
                "volume24h_usd": vol,
                "status": "UNVERIFIED" if unverified else "NEW",
                "comment": reason_uv if unverified else "",
            })

            if cid not in seen:
                if unverified:
                    await safe_send(
                        app,
                        settings.chat_id,
                        (
                            "🟡 <b>ULTRA-EARLY (UNVERIFIED)</b>\n\n"
                            f"<b>{token['name']}</b> ({token['symbol']})\n"
                            f"Возраст: {age} дн\n"
                            f"Market Cap: ${mcap:,.0f}\n"
                            f"Volume 24h: ${vol:,.0f}\n\n"
                            f"Причина: {reason_uv}\n\n"
                            + (
                                "👀 Добавлен в TRACK MODE (ALLOW_UNVERIFIED_TRACK=1)\n"
                                if ALLOW_UNVERIFIED_TRACK
                                else "⛔ По умолчанию не трекаю. Если хочешь трекать — поставь ALLOW_UNVERIFIED_TRACK=1"
                            )
                        ),
                        silent_on_broken_pipe=True,
                    )
                    mark_seen(state, cid)

                    if ALLOW_UNVERIFIED_TRACK:
                        mark_tracked(state, cid)
                        # track meta
                        meta = state.setdefault("tracked_meta", {})
                        meta[str(cid)] = {"ts": time.time(), "symbol": token["symbol"], "name": token["name"]}
                else:
                    await safe_send(
                        app,
                        settings.chat_id,
                        (
                            "⚡ <b>ULTRA-EARLY</b>\n\n"
                            f"<b>{token['name']}</b> ({token['symbol']})\n"
                            f"Возраст: {age} дн\n"
                            f"Market Cap: ${mcap:,.0f}\n"
                            f"Volume 24h: ${vol:,.0f}\n\n"
                            "👀 Добавлен в TRACK MODE\n"
                            "⏳ Ждём появления торгов"
                        ),
                        silent_on_broken_pipe=True,
                    )
                    mark_seen(state, cid)
                    mark_tracked(state, cid)

                    # track meta
                    meta = state.setdefault("tracked_meta", {})
                    meta[str(cid)] = {"ts": time.time(), "symbol": token["symbol"], "name": token["name"]}

        else:
            # log + skip
            sheets.buffer_append({
                "detected_at": now_iso_utc(),
                "cmc_id": cid,
                "symbol": token["symbol"],
                "name": token["name"],
                "slug": token["slug"],
                "age_days": age,
                "market_cap_usd": mcap,
                "volume24h_usd": vol,
                "status": "SKIP",
                "comment": "",
            })

        # ------------------------------
        # TRACK → trading / candles
        # ------------------------------
        if cid not in tracked:
            continue

        binance_ok = check_binance(token["symbol"])
        bybit_ok = check_bybit(token["symbol"])

        market = "NONE"
        if binance_ok:
            market = "BINANCE"
        elif bybit_ok:
            market = "BYBIT"

        if market == "NONE":
            continue

        candles_5m = []
        candles_15m = []

        if market == "BINANCE":
            candles_5m = get_binance_5m(token["symbol"])
            candles_15m = get_binance_15m(token["symbol"])
        else:
            candles_5m = get_bybit_5m(token["symbol"])
            candles_15m = get_bybit_15m(token["symbol"])

        # liquidity gate
        ok_liq, _liq_meta = liquidity_gate(token["symbol"], market, candles_5m, candles_15m)
        if not ok_liq:
            continue

        # ------------------------------
        # FIRST MOVE (5m)
        # ------------------------------
        FIRST_COOLDOWN = 60 * 60  # 1 hour

        if candles_5m:
            fm = first_move_eval(token["symbol"], candles_5m)
            if (
                fm.get("ok")
                and not first_move_sent(state, cid)
                and first_move_cooldown_ok(state, cid, FIRST_COOLDOWN)
            ):
                await safe_send(
                    app,
                    settings.chat_id,
                    fm["text"],
                    silent_on_broken_pipe=True,
                )
                mark_first_move_sent(state, cid, time.time())

        # ------------------------------
        # CONFIRM-LIGHT (15m)
        # ------------------------------
        CONFIRM_COOLDOWN = 2 * 60 * 60  # 2 hours

        if candles_15m:
            cl = confirm_light_eval(token["symbol"], candles_15m)
            if (
                cl.get("ok")
                and not confirm_light_sent(state, cid)
                and confirm_light_cooldown_ok(state, cid, CONFIRM_COOLDOWN)
            ):
                await safe_send(
                    app,
                    settings.chat_id,
                    cl["text"],
                    silent_on_broken_pipe=True,
                )
                mark_confirm_light_sent(state, cid, time.time())

    safe_sheets_flush(sheets)
    save_state(state)


# =========================
# main
# =========================

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

    # startup-guard: not more than 1 per hour
    state = load_state()
    if not startup_sent_recent(state, cooldown_sec=3600):
        await safe_send(
            app,
            settings.chat_id,
            (
                "📡 Listings Radar запущен\n"
                "Цепочка: ULTRA → TRACK → FIRST MOVE → CONFIRM-LIGHT\n"
                "SUMMARY: ENTRY + EXIT + VERDICT\n"
                "DEBUG: OFF"
            ),
            silent_on_broken_pipe=True,
        )
        mark_startup_sent(state)
        save_state(state)

    while True:
        try:
            await scan_once(app, settings, cmc, sheets)
        except Exception as e:
            if not _is_broken_pipe(e):
                await safe_send(app, settings.chat_id, f"❌ Ошибка: {e}", parse_mode=None)
        await asyncio.sleep(settings.check_interval_min * 60)


if __name__ == "__main__":
    asyncio.run(main())
