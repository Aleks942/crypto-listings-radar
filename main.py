import asyncio
import time
from telegram.constants import ParseMode
from telegram.ext import Application

from config import Settings
from cmc import CMCClient, age_days
from sheets import SheetsClient, now_iso_utc
from state import load_state, save_state, seen_ids, mark_seen

from signals import check_confirm_light
CONFIRM_URL = "https://web-production-2e833.up.railway.app/webhook/listing"

# --------------------------------------------------
# ОСНОВНОЙ СКАН
# --------------------------------------------------

async def scan_once(app, settings, cmc, sheets):
    state = load_state()
    seen = seen_ids(state)

    coins = cmc.fetch_recent_listings(limit=settings.limit)

    sent_ultra = 0
    sent_confirm_light = 0

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

        # --------------------------------------------------
        # GOOGLE SHEETS — ВСЁ
        # --------------------------------------------------

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

        # --------------------------------------------------
        # ULTRA-EARLY (первый отбор)
        # --------------------------------------------------
from confirm_sender import send_to_confirm_engine

        if age is not None and age <= 1 and vol >= 500_000:
            if cid not in seen:
                text = (
                    f"⚡ *ULTRA-EARLY*\n\n"
                    f"*{token['name']}* ({token['symbol']})\n"
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
                mark_seen(state, cid)

        # --------------------------------------------------
        # CONFIRM-LIGHT (начало разгона)
        # --------------------------------------------------

        prev_snapshot = state.get("snapshots", {}).get(str(cid))

        confirm_light = check_confirm_light(token, prev_snapshot)

        if confirm_light:
            text = (
                f"🟢 *CONFIRM-LIGHT*\n\n"
                f"*{token['name']}* ({token['symbol']})\n"
                f"Возраст: {confirm_light['age_min']} мин\n"
                f"Рост объёма: x{confirm_light['volume_x']}\n"
                f"Интервал: {confirm_light['minutes']} мин\n\n"
                f"⚠️ Ранний вход (малый объём)"
            )

            await app.bot.send_message(
                chat_id=settings.chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
            )

            sent_confirm_light += 1

        # --------------------------------------------------
        # СОХРАНЯЕМ СНИМОК ДЛЯ СЛЕДУЮЩЕЙ ПРОВЕРКИ
        # --------------------------------------------------

        state.setdefault("snapshots", {})[str(cid)] = {
            "volume_24h": vol,
            "price": price,
            "ts": now_ts,
        }

    sheets.flush()
    save_state(state)

    # --------------------------------------------------
    # ИТОГОВЫЕ СООБЩЕНИЯ
    # --------------------------------------------------

    if sent_ultra:
        await app.bot.send_message(
            chat_id=settings.chat_id,
            text=f"✅ ULTRA сигналов: {sent_ultra}",
        )

    if sent_confirm_light:
        await app.bot.send_message(
            chat_id=settings.chat_id,
            text=f"🟢 CONFIRM-LIGHT сигналов: {sent_confirm_light}",
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
            "Telegram = ULTRA / CONFIRM-LIGHT\n"
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

