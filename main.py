import asyncio
import os
import time
from telegram.constants import ParseMode
from telegram.ext import Application

from config import Settings
from cmc import CMCClient, age_days
from sheets import SheetsClient, now_iso_utc

from confirm_entry_client import send_to_confirm_entry

from state import (
    load_state,
    save_state,
    seen_ids,
    mark_seen,
    tracked_ids,
    mark_tracked,
    first_move_cooldown_ok,
    mark_first_move_sent,
    confirm_light_sent,
    mark_confirm_light_sent,
    confirm_light_cooldown_ok,
    startup_sent_recent,
    mark_startup_sent,
    ultra_seen,
    mark_ultra_seen,
)

from detect_trading import check_binance, check_bybit, check_bybit_linear
from first_move import first_move_eval
from confirm_light import confirm_light_eval

from candles_binance import get_candles_5m as get_binance_5m
from candles_bybit import get_candles_5m as get_bybit_5m

# ================= EDGE LAYERS =================
from crowd_engine import crowd_engine_ok

from liquidity_growth import liquidity_growth_ok
from liquidity_memory import liquidity_memory_ok
from funding_flow import funding_flow_ok as funding_crowd_ok

from whale_trap import whale_trap_detect

# 15m candles optional
try:
    from candles_binance import get_candles_15m as get_binance_15m
except Exception:
    get_binance_15m = None

try:
    from candles_bybit import get_candles_15m as get_bybit_15m
except Exception:
    get_bybit_15m = None


# ================= ENV =================
FIRST_COOLDOWN = int(os.getenv("FIRST_COOLDOWN_SEC", str(60 * 60)))
CONFIRM_COOLDOWN = int(os.getenv("CONFIRM_COOLDOWN_SEC", str(2 * 60 * 60)))
STARTUP_GUARD_SEC = int(os.getenv("STARTUP_GUARD_SEC", "3600"))

ANTI_SCAM_MIN_CANDLES = int(os.getenv("ANTI_SCAM_MIN_CANDLES", "25"))
ANTI_SCAM_MAX_RANGE = float(os.getenv("ANTI_SCAM_MAX_RANGE", "2.5"))
ANTI_SCAM_VOL_DROP_K = float(os.getenv("ANTI_SCAM_VOL_DROP_K", "0.7"))


def _now():
    return float(time.time())


# ================= SAFE SEND =================
async def safe_send(app, chat_id, text, parse_mode=ParseMode.HTML, retries=3):
    last_err = None
    for _ in range(retries):
        try:
            return await app.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
        except Exception as e:
            last_err = e
            await asyncio.sleep(1.5)
    raise last_err


# ================= DETECT TRADING =================
def detect_trading(symbol):
    binance_ok = check_binance(symbol)
    bybit_spot_ok = check_bybit(symbol)
    bybit_linear_ok = check_bybit_linear(symbol)

    return {
        "binance": binance_ok,
        "bybit_spot": bybit_spot_ok,
        "bybit_linear": bybit_linear_ok,
        "any": binance_ok or bybit_spot_ok or bybit_linear_ok,
    }


# ================= SHARP FILTER =================
def anti_scam_filter(candles):

    if not candles or len(candles) < ANTI_SCAM_MIN_CANDLES:
        return False

    try:
        highs = [float(c[2]) for c in candles]
        lows = [float(c[3]) for c in candles]
        volumes = [float(c[5]) for c in candles]
    except Exception:
        return False

    low_min = min(lows)
    high_max = max(highs)

    if low_min <= 0:
        return False

    price_range = (high_max - low_min) / max(low_min, 1e-12)

    if price_range > ANTI_SCAM_MAX_RANGE:
        return False

    half = len(volumes) // 2
    v1 = sum(volumes[:half])
    v2 = sum(volumes[half:])

    if v1 > 0 and v2 < v1 * ANTI_SCAM_VOL_DROP_K:
        return False

    return True


# ================= SCAN LOOP =================
async def scan_once(app, settings, cmc, sheets):

    state = load_state()
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

        if age is None or age > settings.max_age_days or vol < settings.min_volume_usd:
            continue

        symbol = (coin.get("symbol") or "").strip()
        name = (coin.get("name") or "").strip()

        # ================= ULTRA =================
        if cid not in seen and not ultra_seen(state, cid):

            await safe_send(
                app,
                settings.chat_id,
                f"⚡ <b>ULTRA-EARLY</b>\n(Раннее обнаружение листинга)\n\n<b>{name}</b> ({symbol})",
            )

            sheets.buffer_append({
                "detected_at": now_iso_utc(),
                "cmc_id": cid,
                "symbol": symbol,
                "status": "ULTRA",
            })

            mark_seen(state, cid)
            mark_ultra_seen(state, cid)
            save_state(state)

        already_tracked = cid in tracked

        # ================= TRACK =================
        if not already_tracked:

            t = detect_trading(symbol)
            if not t["any"]:
                continue

            mark_tracked(state, cid)
            save_state(state)

            sheets.buffer_append({
                "detected_at": now_iso_utc(),
                "cmc_id": cid,
                "symbol": symbol,
                "status": "TRACK",
            })
        else:
            t = detect_trading(symbol)

        # ================= CROWD FLOW =================
        try:
            if funding_crowd_ok(symbol):

                await safe_send(
                    app,
                    settings.chat_id,
                    f"🟢 <b>CROWD FLOW</b>\n(Толпа вошла — рынок заряжается)\n\n<b>{symbol}</b>",
                )

                sheets.buffer_append({
                    "detected_at": now_iso_utc(),
                    "cmc_id": cid,
                    "symbol": symbol,
                    "status": "CROWD_FLOW",
                })
        except Exception:
            pass

        # ================= FIRST MOVE =================
        if not confirm_light_sent(state, cid):

            candles_5m = []

            if t["binance"]:
                candles_5m = get_binance_5m(symbol)
            elif t["bybit_spot"] or t["bybit_linear"]:
                candles_5m = get_bybit_5m(symbol)

            if (
                candles_5m
                and anti_scam_filter(candles_5m)
                and liquidity_growth_ok(candles_5m)
                and liquidity_memory_ok(symbol, candles_5m)
            ):

                fm = first_move_eval(symbol, candles_5m)

                if fm.get("ok") and first_move_cooldown_ok(state, cid, FIRST_COOLDOWN):

                    await safe_send(
                        app,
                        settings.chat_id,
                        fm["text"] + "\n\n(Импульс начался — возможный ранний вход)",
                    )

                    sheets.buffer_append({
                        "detected_at": now_iso_utc(),
                        "cmc_id": cid,
                        "symbol": symbol,
                        "status": "FIRST_MOVE",
                    })

                    mark_first_move_sent(state, cid, _now())
                    save_state(state)

        # ================= CONFIRM LIGHT =================
        candles_15m = []

        if t["binance"] and get_binance_15m:
            candles_15m = get_binance_15m(symbol)
        elif (t["bybit_spot"] or t["bybit_linear"]) and get_bybit_15m:
            candles_15m = get_bybit_15m(symbol)

        if candles_15m:

            cl = confirm_light_eval(symbol, candles_15m)

            if cl.get("ok") and confirm_light_cooldown_ok(state, cid, CONFIRM_COOLDOWN):

                exchange = "BINANCE" if t["binance"] else "BYBIT"

                mark_confirm_light_sent(state, cid, _now())
                save_state(state)

                sheets.buffer_append({
                    "detected_at": now_iso_utc(),
                    "cmc_id": cid,
                    "symbol": symbol,
                    "status": "CONFIRM_LIGHT",
                })

                send_to_confirm_entry(
                    symbol=symbol,
                    exchange=exchange,
                    tf="15m",
                    candles=candles_15m,
                    mode_hint="CONFIRM_LIGHT",
                )

    sheets.flush()
    save_state(state)


# ================= MAIN =================
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

    state = load_state()

    if not startup_sent_recent(state, cooldown_sec=STARTUP_GUARD_SEC):

        await safe_send(
            app,
            settings.chat_id,
            "📡 Listings Radar запущен\n(Радар листингов активирован)",
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

