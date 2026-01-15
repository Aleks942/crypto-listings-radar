import asyncio
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

# ==================================================
# ОСНОВНОЙ СКАН
# ==================================================

async def scan_once(app, settings, cmc, sheets):
    state = load_state()
    seen = seen_ids(state)
    tracked = tracked_ids(state)

    coins = cmc.fetch_recent_listings(limit=settings.limit)
    now_ts = time.time()
print(f"[SCAN] fetched {len(coins)} coins from CMC")

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
        # GOOGLE SHEETS (лог)
        # ------------------------------
        sheets.buffer_append({
            "detected_at": now_iso_utc(),
            "cmc_id": cid,
            "symbol": token["symbol"],
            "name": token["name"],
            "slug": token["slug"],
            "age_days": age,
            "market_cap_usd": mcap,
            "volume24h_usd": vol,
            "status": "NEW",
            "comment": "",
        })

        # ------------------------------
        # ULTRA-EARLY → TRACK MODE
        # ------------------------------
        print(f"[ULTRA] {token['symbol']} age={age} vol={vol:,.0f}")

        if age is not None and age <= 1 and vol >= 500_000:
            if cid not in seen:
                await app.bot.send_message(
                    chat_id=settings.chat_id,
                    text=(
                        "⚡ <b>ULTRA-EARLY</b>\n\n"
                        f"<b>{token['name']}</b> ({token['symbol']})\n"
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

        # ------------------------------
        # TRACK → ТОРГИ
        # ------------------------------
        if cid not in tracked:
            continue

        binance_ok = check_binance(token["symbol"])
        bybit_ok = check_bybit(token["symbol"])

        if not binance_ok and not bybit_ok:
            continue

        market = "Binance" if binance_ok else "Bybit"

        # ------------------------------
        # FIRST MOVE (5m)
        # ------------------------------
        candles_5m = []
        if binance_ok:
            candles_5m = get_binance_5m(token["symbol"])
        elif bybit_ok:
            candles_5m = get_bybit_5m(token["symbol"])
            if binance_ok or bybit_ok:
    print(f"[TRADING] {token['symbol']} on {'Binance' if binance_ok else 'Bybit'}")


        FIRST_COOLDOWN = 60 * 60  # 1 час

        if candles_5m:
            fm = first_move_eval(token["symbol"], candles_5m, market)
            if (
                fm.get("ok")
                and not first_move_sent(state, cid)
                and first_move_cooldown_ok(state, cid, FIRST_COOLDOWN)
            ):
                await app.bot.send_message(
                    chat_id=settings.chat_id,
                    text=fm["text"],
                    parse_mode=ParseMode.HTML,
                )
                mark_first_move_sent(state, cid, time.time())

        # ------------------------------
        # CONFIRM-LIGHT (15m)
        # ТОЛЬКО если был FIRST MOVE
        # ------------------------------
        if not first_move_sent(state, cid):
            continue

        candles_15m = []
        if binance_ok:
            candles_15m = get_binance_15m(token["symbol"])
        elif bybit_ok:
            candles_15m = get_bybit_15m(token["symbol"])

        CONFIRM_COOLDOWN = 2 * 60 * 60  # 2 часа

        if candles_15m:
            cl = confirm_light_eval(token["symbol"], candles_15m, market)
            if (
                cl.get("ok")
                and not confirm_light_sent(state, cid)
                and confirm_light_cooldown_ok(state, cid, CONFIRM_COOLDOWN)
            ):
                await app.bot.send_message(
                    chat_id=settings.chat_id,
                    text=cl["text"],
                    parse_mode=ParseMode.HTML,
                )
                mark_confirm_light_sent(state, cid, time.time())

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

    await app.bot.send_message(
        chat_id=settings.chat_id,
        text=(
            "📡 Listings Radar запущен\n"
            "Цепочка: ULTRA → TRACK → FIRST MOVE → CONFIRM-LIGHT\n"
            "SUMMARY MODE: ENTRY + EXIT + VERDICT"
        ),
        parse_mode=ParseMode.HTML,
    )

    while True:
        try:
            await scan_once(app, settings, cmc, sheets)
        except Exception as e:
            await app.bot.send_message(
                chat_id=settings.chat_id,
                text=f"❌ Ошибка: {e}",
            )
        await asyncio.sleep(settings.check_interval_min * 60)

if __name__ == "__main__":
    asyncio.run(main())
