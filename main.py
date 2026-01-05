import asyncio
from datetime import datetime, timezone
from telegram.ext import Application
from telegram.constants import ParseMode

from config import Settings
from cmc import CMCClient, age_days, cmc_urls
from sheets import SheetsClient, now_iso_utc
from state import load_state, save_state, mark_seen, mark_tracked, seen_ids


# ---------------- utils ----------------

def is_daytime():
    hour = datetime.now().hour
    return 7 <= hour < 23


def spike_grade(vol_mult, price_pct, pairs_added, cap):
    if vol_mult >= 2.5 and price_pct >= 20 and pairs_added >= 3 and cap <= 30_000_000:
        return "A"
    if vol_mult >= 2.0 and price_pct >= 10 and pairs_added >= 1 and cap <= 50_000_000:
        return "B"
    return "C"


# ---------------- core ----------------

async def scan(app, settings, cmc, sheets):
    state = load_state()
    seen = seen_ids(state)

    coins = cmc.fetch_recent_listings(limit=settings.limit)
    spikes_today = state.get("spikes_today", 0)

    for coin in coins:
        cid = int(coin.get("id") or 0)
        if not cid or cid in seen:
            continue

        mark_seen(state, cid)

        age = age_days(coin.get("date_added"))
        usd = coin.get("quote", {}).get("USD", {})
        volume = float(usd.get("volume_24h") or 0)
        cap = float(usd.get("market_cap") or 0)
        price = float(usd.get("price") or 0)
        pairs = int(coin.get("num_market_pairs") or 0)

        # ---- always log to Sheets ----
        sheets.append_listing({
            "cmc_id": cid,
            "detected_at": now_iso_utc(),
            "symbol": coin.get("symbol"),
            "name": coin.get("name"),
            "slug": coin.get("slug"),
            "age_days": age,
            "market_cap": cap,
            "volume_24h": volume,
            "price": price,
            "pairs": pairs,
            "status": "NEW"
        })

        # ---- ULTRA (Telegram) ----
        if age <= 1 and volume >= 500_000:
            await app.bot.send_message(
                chat_id=settings.chat_id,
                parse_mode=ParseMode.MARKDOWN,
                text=(
                    f"⚡ *ULTRA-EARLY*\n\n"
                    f"{coin['name']} ({coin['symbol']})\n"
                    f"Возраст: {age} дн | Пары: {pairs}\n"
                    f"Market Cap: ${cap/1e6:.2f}M\n"
                    f"Volume 24h: ${volume/1e6:.2f}M\n\n"
                    f"🔍 Отбор, не вход"
                )
            )

        # ---- SPIKE ----
        tracked = cid in state.get("tracked", {})
        vol_mult = state.get("last_volume", {}).get(cid, 0)
        price_prev = state.get("last_price", {}).get(cid, price)
        price_pct = ((price - price_prev) / price_prev * 100) if price_prev else 0
        pairs_prev = state.get("last_pairs", {}).get(cid, pairs)
        pairs_added = pairs - pairs_prev

        if tracked and vol_mult >= 2.0 and spikes_today < 2 and cap <= 50_000_000:
            grade = spike_grade(vol_mult, price_pct, pairs_added, cap)

            if grade != "C":
                state["spikes_today"] = spikes_today + 1

                await app.bot.send_message(
                    chat_id=settings.chat_id,
                    parse_mode=ParseMode.MARKDOWN,
                    text=(
                        f"🔥 *SPIKE {grade} — ВХОД*\n\n"
                        f"{coin['name']} ({coin['symbol']})\n"
                        f"Цена: ${price}\n"
                        f"Market Cap: ${cap/1e6:.2f}M\n\n"
                        f"*Причина:*\n"
                        f"• Volume x{vol_mult:.2f}\n"
                        f"• Цена +{price_pct:.1f}%\n"
                        f"• Пары +{pairs_added}\n\n"
                        f"*План:*\n"
                        f"🟢 TP1: +35%\n"
                        f"🔴 Trail: -20%"
                    )
                )

        # ---- remember last values ----
        state.setdefault("last_volume", {})[cid] = volume
        state.setdefault("last_price", {})[cid] = price
        state.setdefault("last_pairs", {})[cid] = pairs

    save_state(state)


# ---------------- entry ----------------

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
            "📡 *Listings Radar запущен*\n"
            "⏱ Днём: каждые 20 мин\n"
            "🌙 Ночью: каждые 60 мин\n\n"
            "Telegram = только ULTRA и SPIKE\n"
            "🆕 пишутся в Google Sheets"
        ),
        parse_mode=ParseMode.MARKDOWN,
    )

    while True:
        try:
            await scan(app, settings, cmc, sheets)
        except Exception as e:
            await app.bot.send_message(
                chat_id=settings.chat_id,
                text=f"❌ Ошибка: {e}",
            )

        sleep_min = 20 if is_daytime() else 60
        await asyncio.sleep(sleep_min * 60)


if __name__ == "__main__":
    asyncio.run(main())

