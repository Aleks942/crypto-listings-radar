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

from detect_trading import check_binance, check_bybit, check_bybit_linear
from first_move import first_move_eval
from confirm_light import confirm_light_eval

from candles_binance import get_candles_5m as get_binance_5m
from candles_bybit import get_candles_5m as get_bybit_5m

# 15m опционально
try:
    from candles_binance import get_candles_15m as get_binance_15m
except Exception:
    get_binance_15m = None

try:
    from candles_bybit import get_candles_15m as get_bybit_15m
except Exception:
    get_bybit_15m = None


# ==================================================
# ENV knobs
# ==================================================
WATCH_TTL_HOURS = int((os.getenv("WATCH_TTL_HOURS", "24") or "24").strip())
TRACK_TTL_HOURS = int((os.getenv("TRACK_TTL_HOURS", "72") or "72").strip())  # tracked держим дольше
ALLOW_UNVERIFIED_TRACK = (os.getenv("ALLOW_UNVERIFIED_TRACK", "0") or "0").strip() == "1"
DEBUG = (os.getenv("DEBUG", "OFF") or "OFF").strip().upper() == "ON"

FIRST_COOLDOWN = int((os.getenv("FIRST_COOLDOWN_SEC", str(60 * 60)) or str(60 * 60)).strip())
CONFIRM_COOLDOWN = int((os.getenv("CONFIRM_COOLDOWN_SEC", str(2 * 60 * 60)) or str(2 * 60 * 60)).strip())
STARTUP_GUARD_SEC = int((os.getenv("STARTUP_GUARD_SEC", "3600") or "3600").strip())


# ==================================================
# Anti-duplicate helpers
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
    raise last_err


def _now() -> float:
    return float(time.time())


def _meta_get(state: dict, key: str) -> dict:
    return (state.get(key, {}) or {}) if isinstance(state.get(key, {}), dict) else {}


def _ttl_cleanup(state: dict, key_list: str, key_meta: str, ttl_hours: int) -> int:
    ttl_sec = max(1, ttl_hours) * 3600
    now = _now()

    ids = set(state.get(key_list, []) or [])
    meta = _meta_get(state, key_meta)

    removed = 0
    keep = []
    for cid in ids:
        k = str(cid)
        ts = float((meta.get(k) or {}).get("ts", 0.0) or 0.0)
        if ts <= 0 or (now - ts) >= ttl_sec:
            removed += 1
            meta.pop(k, None)
        else:
            keep.append(int(cid))

    if removed:
        state[key_list] = sorted(keep)
        state[key_meta] = meta

    return removed


def mark_meta(state: dict, meta_key: str, cid: int, symbol: str, name: str):
    meta = _meta_get(state, meta_key)
    meta[str(cid)] = {"ts": _now(), "symbol": symbol, "name": name}
    state[meta_key] = meta


def watch_ids(state: dict) -> set[int]:
    return set(state.get("watch", []) or [])


def mark_watch(state: dict, cid: int):
    s = set(state.get("watch", []) or [])
    s.add(int(cid))
    state["watch"] = sorted(s)


def unwatch(state: dict, cid: int):
    s = set(state.get("watch", []) or [])
    if int(cid) in s:
        s.remove(int(cid))
    state["watch"] = sorted(s)


def trading_found_sent(state: dict, cid: int) -> bool:
    sent = _meta_get(state, "trading_found_sent")
    return str(cid) in sent


def mark_trading_found_sent(state: dict, cid: int):
    sent = _meta_get(state, "trading_found_sent")
    sent[str(cid)] = _now()
    state["trading_found_sent"] = sent


# ==================================================
# Trading detector (binance/bybit/linear)
# ==================================================
def detect_trading(symbol: str) -> dict:
    binance_ok = check_binance(symbol)
    bybit_spot_ok = check_bybit(symbol)
    bybit_linear_ok = check_bybit_linear(symbol)
    return {
        "binance": binance_ok,
        "bybit_spot": bybit_spot_ok,
        "bybit_linear": bybit_linear_ok,
        "any": (binance_ok or bybit_spot_ok or bybit_linear_ok),
    }


# ==================================================
# scan
# ==================================================
async def scan_once(app: Application, settings: Settings, cmc: CMCClient, sheets: SheetsClient):
    state = load_state()

    # TTL уборка
    _ttl_cleanup(state, "watch", "watch_meta", WATCH_TTL_HOURS)
    _ttl_cleanup(state, "tracked", "tracked_meta", TRACK_TTL_HOURS)

    seen = seen_ids(state)
    watch = watch_ids(state)
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

        # ЛОГ в таблицу (аудит)
        sheets.buffer_append({
            "detected_at": now_iso_utc(),
            "cmc_id": cid,
            "symbol": symbol,
            "name": name,
            "slug": slug,
            "age_days": age,
            "market_cap_usd": mcap,
            "volume24h_usd": vol,
            "status": "SCAN",
            "comment": "",
        })

        # фильтр по возрасту/объёму
        if age is None or age > settings.max_age_days or vol < settings.min_volume_usd:
            continue

        # UNVERIFIED фильтр
        reason = is_unverified_token(symbol, name)
        if reason and not ALLOW_UNVERIFIED_TRACK:
            # антидубль: только если не видели
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

        # -------- ULTRA → WATCH (первичное)
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
                    "👀 Добавлен в <b>WATCH MODE</b>\n"
                    "⏳ Ждём появления торгов на Binance/Bybit"
                ),
                parse_mode=ParseMode.HTML,
            )
            mark_seen(state, cid)
            mark_watch(state, cid)
            mark_meta(state, "watch_meta", cid, symbol, name)
            save_state(state)

        # -------- WATCH → (TRADING FOUND) → TRACK
        # если уже в tracked — пропускаем
        if cid in tracked:
            continue

        # если не в watch — тоже не занимаемся
        if cid not in watch:
            continue

        t = detect_trading(symbol)
        if not t["any"]:
            continue

        # нашли торги: один раз сообщаем и переводим в TRACK
        if not trading_found_sent(state, cid):
            where = []
            if t["binance"]:
                where.append("Binance spot")
            if t["bybit_spot"]:
                where.append("Bybit spot")
            if t["bybit_linear"]:
                where.append("Bybit perp (linear)")

            await safe_send(
                app,
                settings.chat_id,
                (
                    "✅ <b>TRADING FOUND</b>\n\n"
                    f"<b>{name}</b> ({symbol})\n"
                    f"Где: <b>{', '.join(where)}</b>\n\n"
                    "➡️ Перевожу в <b>TRACK MODE</b> и начинаю ловить FIRST MOVE"
                ),
                parse_mode=ParseMode.HTML,
            )
            mark_trading_found_sent(state, cid)

        # переводим в tracked и убираем из watch
        mark_tracked(state, cid)
        mark_meta(state, "tracked_meta", cid, symbol, name)
        unwatch(state, cid)
        save_state(state)

        # -------- TRACK → FIRST MOVE / CONFIRM
        # свечи 5m: берём приоритетом Binance, потом Bybit spot, потом Bybit linear (пока как Bybit spot источник)
        candles_5m = []
        if t["binance"]:
            candles_5m = get_binance_5m(symbol)
        elif t["bybit_spot"] or t["bybit_linear"]:
            candles_5m = get_bybit_5m(symbol)

        if candles_5m:
            fm = first_move_eval(symbol, candles_5m)
            if (
                fm.get("ok")
                and not first_move_sent(state, cid)
                and first_move_cooldown_ok(state, cid, FIRST_COOLDOWN)
            ):
                await safe_send(app, settings.chat_id, fm["text"], parse_mode=ParseMode.HTML)
                mark_first_move_sent(state, cid, _now())
                save_state(state)

        # CONFIRM 15m — если функции есть
        if get_binance_15m is None and get_bybit_15m is None:
            continue

        candles_15m = []
        if t["binance"] and get_binance_15m is not None:
            candles_15m = get_binance_15m(symbol)
        elif (t["bybit_spot"] or t["bybit_linear"]) and get_bybit_15m is not None:
            candles_15m = get_bybit_15m(symbol)

        if candles_15m:
            cl = confirm_light_eval(symbol, candles_15m)
            if (
                cl.get("ok")
                and not confirm_light_sent(state, cid)
                and confirm_light_cooldown_ok(state, cid, CONFIRM_COOLDOWN)
            ):
                await safe_send(app, settings.chat_id, cl["text"], parse_mode=ParseMode.HTML)
                mark_confirm_light_sent(state, cid, _now())
                save_state(state)

    sheets.flush()
    save_state(state)


# ==================================================
# MAIN LOOP
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

    # startup guard
    state = load_state()
    if not startup_sent_recent(state, cooldown_sec=STARTUP_GUARD_SEC):
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
        mark_startup_sent(state)
        save_state(state)

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

