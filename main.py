import asyncio
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

from config import Settings
from cmc import CMCClient, age_days, cmc_urls
from sheets import SheetsClient, now_iso_utc
from state import load_state, save_state, seen_ids, mark_seen


async def scan_once(app, settings, cmc, sheets):
    state = load_state()
    seen = seen_ids(state)

    coins = cmc.fetch_recent_listings(limit=settings.limit)
    sent_ultra = 0

    for coin in coins:
        cid = int(coin.get("id") or 0)
        if not cid or cid in seen:
            continue

        mark_seen(state, cid)

        age = age_days(coin.get("date_added"))
        usd = (coin.get("quote") or {}).get("USD") or {}
        vol = float(usd.get("volume_24h") or 0)
        mcap = float(usd.get("market_cap") or 0)

        # ВСЁ пишем в Google Sheets
        sheets.buffer_append({
            "detected_at": now_iso_utc(),
            "cmc_id": cid,
            "symbol": coin.get("symbol"),
            "name": coin.get("name"),
            "slug": coin.get("slug"),
            "age_days": age,
            "market_cap_usd": mcap,
            "volume24h_usd": vol,
            "status": "NEW",
            "comment": "",
        })

        # TELEGRAM — ТОЛЬКО ULTRA
        if age is not None and age <= 1 and vol >= 500_000:
            text = (
                f"⚡ *ULTRA-EARLY*\n\n"
                f"*{coin['name']}* ({coin['symbol']})\n"
                f"Возраст: {age} дн\n"
                f"Market Cap: ${mcap:,.0f}\n"
                f"Volume 24h: ${vol:,.0f}\n\n"
                f"🔍 Отбор, не вход"
            )
            await app.bot.send_message(
                chat_id=settings.chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
            )
            sent_ultra += 1

    sheets.flush()
    save_state(state)

    if sent_ultra:
        await app.bot.send_message(
            chat_id=settings.chat_id,
            text=f"✅ ULTRA сигналов: {sent_ultra}",
        )


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
            "Telegram = ULTRA / SPIKE\n"
            "🆕 → Google Sheets (batch)"
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
