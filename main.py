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
)

# --------------------------------------------------
# ОСНОВНОЙ СКАН
# --------------------------------------------------

async def scan_once(app, settings, cmc, sheets):
    state = load_state()

    seen = seen_ids(state)
    tracked = tracked_ids(state)

    coins = cmc.fetch_recent_listings(limit=settings.limit)

    sent_ultra = 0
    sent_tracked = 0

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
        if age is not None and age <= 1 and vol >= 500_000:
            if cid not in seen:
                text = (
                    "⚡ <b>ULTRA-EARLY</b>\n\n"
                    f"<b>{token['name']}</b> ({token['symbol']})\n"
                    f"Возраст: {age} дн\n"
                    f"Market Cap: ${mcap:,.0f}\n"
                    f"Volume 24h: ${vol:,.0f}\n\n"
                    "👀 Добавлен в TRACK MODE\n"
                    "⏳ Ждём появления торгов"
                )

                await app.bot.send_message(
                    chat_id=settings.chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                )

                mark_seen(state, cid)
                mark_tracked(state, cid)

                sent_ultra += 1
                sent_tracked += 1

    sheets.flush()
    save_state(state)

    # ------------------------------
    # ИТОГ
    # ------------------------------
    if sent_ultra:
        await app.bot.send_message(
            chat_id=settings.chat_id,
            text=f"✅ ULTRA найдено: {sent_ultra}\n👀 В TRACK MODE: {sent_tracked}",
        )


# --------------------------------------------------
# MAIN LOOP
# --------------------------------------------------

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
            "Режим: ULTRA → TRACK\n"
            "🆕 → Google Sheets"
        ),
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

