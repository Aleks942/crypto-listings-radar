import asyncio
from typing import Dict, Any, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
)

from config import Settings
from cmc import CMCClient, age_days, cmc_urls
from sheets import SheetsClient, now_iso_utc
from state import (
    load_state,
    save_state,
    mark_seen,
    mark_tracked,
    seen_ids,
)


def fmt_money(x: Optional[float]) -> str:
    if x is None:
        return "—"
    try:
        x = float(x)
    except Exception:
        return "—"
    if x >= 1_000_000_000:
        return f"${x/1_000_000_000:.2f}B"
    if x >= 1_000_000:
        return f"${x/1_000_000:.2f}M"
    if x >= 1_000:
        return f"${x/1_000:.2f}K"
    return f"${x:.2f}"


def build_message(coin: Dict[str, Any], age: int, market_cap: float, vol24: float, urls: Dict[str, str]) -> str:
    return (
        f"🆕 *Новая монета обнаружена*\n\n"
        f"*{coin.get('name')}* (`{coin.get('symbol')}`)\n"
        f"CMC ID: `{coin.get('id')}`\n"
        f"Slug: `{coin.get('slug')}`\n"
        f"Дата добавления: `{coin.get('date_added')}`\n"
        f"Возраст: *{age}* дн.\n\n"
        f"Market Cap: *{fmt_money(market_cap)}*\n"
        f"Volume 24h: *{fmt_money(vol24)}*\n\n"
        f"Ссылки:\n"
        f"• CoinMarketCap: {urls['cmc']}\n"
        f"• Markets: {urls['markets']}"
    )


def build_keyboard(cmc_url: str, markets_url: str, cmc_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔎 CoinMarketCap", url=cmc_url),
            InlineKeyboardButton("💱 Где купить", url=markets_url),
        ],
        [
            InlineKeyboardButton("⭐ Добавить в отслеживаемые", callback_data=f"track:{cmc_id}"),
        ],
    ])


def passes_filters(coin: Dict[str, Any], max_age_days: int, min_volume_usd: float) -> Optional[Dict[str, Any]]:
    age = age_days(coin.get("date_added", ""))
    if age is None or age > max_age_days:
        return None

    usd = (coin.get("quote") or {}).get("USD") or {}
    market_cap = float(usd.get("market_cap") or 0)
    vol24 = float(usd.get("volume_24h") or 0)

    if vol24 < min_volume_usd:
        return None

    slug = (coin.get("slug") or "").strip()
    if not slug:
        return None

    return {
        "age": age,
        "market_cap": market_cap,
        "vol24": vol24,
        "slug": slug,
    }


async def scan_once(app: Application, settings: Settings, cmc: CMCClient, sheets: SheetsClient):
    state = load_state()
    seen = seen_ids(state)

    coins = cmc.fetch_recent_listings(limit=settings.limit)
    sent = 0

    for coin in coins:
        cid = int(coin.get("id") or 0)
        if not cid or cid in seen:
            continue

        mark_seen(state, cid)
        metrics = passes_filters(coin, settings.max_age_days, settings.min_volume_usd)
        if not metrics:
            continue

        urls = cmc_urls(metrics["slug"])
        text = build_message(
            coin,
            metrics["age"],
            metrics["market_cap"],
            metrics["vol24"],
            urls,
        )
        keyboard = build_keyboard(urls["cmc"], urls["markets"], cid)

        sheets.append_listing({
            "cmc_id": cid,
            "detected_at": now_iso_utc(),
            "symbol": coin.get("symbol"),
            "name": coin.get("name"),
            "slug": metrics["slug"],
            "date_added": coin.get("date_added"),
            "age_days": metrics["age"],
            "market_cap_usd": metrics["market_cap"],
            "volume24h_usd": metrics["vol24"],
            "cmc_url": urls["cmc"],
            "markets_url": urls["markets"],
            "status": "NEW",
        })

        await app.bot.send_message(
            chat_id=settings.chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=keyboard,
        )
        sent += 1

    save_state(state)
    if sent:
        await app.bot.send_message(
            chat_id=settings.chat_id,
            text=f"✅ Listings Radar: отправлено сигналов: {sent}",
        )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data.startswith("track:"):
        cid = int(data.split(":", 1)[1])
        state = load_state()
        mark_tracked(state, cid)
        save_state(state)

        sheets: SheetsClient = context.application.bot_data["sheets"]
        sheets.mark_status(cid, "TRACK")

        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(f"⭐ Добавлено в отслеживаемые: CMC_ID {cid}")


async def main():
    settings = Settings.load()

    app = Application.builder().token(settings.bot_token).build()
    cmc = CMCClient(settings.cmc_api_key)
    sheets = SheetsClient(
        settings.google_sheet_url,
        settings.google_service_account_json,
        settings.sheet_tab_name,
    )

    app.bot_data["sheets"] = sheets
    app.add_handler(CallbackQueryHandler(on_callback))

    await app.initialize()
    await app.start()
    await app.bot.send_message(
        chat_id=settings.chat_id,
        text=(
            "📡 *Listings Radar запущен*\n"
            f"• Интервал: {settings.check_interval_min} мин\n"
            f"• Макс. возраст: {settings.max_age_days} дн\n"
            f"• Мин. объём 24h: ${int(settings.min_volume_usd)}"
        ),
        parse_mode=ParseMode.MARKDOWN,
    )

    while True:
        try:
            await scan_once(app, settings, cmc, sheets)
        except Exception as e:
            await app.bot.send_message(
                chat_id=settings.chat_id,
                text=f"❌ Ошибка Listings Radar: {e}",
            )
       await asyncio.sleep(settings.check_interval_min * 60)

