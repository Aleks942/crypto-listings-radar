import asyncio
from typing import Dict, Any, Optional, Tuple

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
    tracked_ids,
    save_watch_volume,
    get_watch_volume,
    spike_sent_ids,
    mark_spike_sent,
    clear_spike_sent,
)


# --- Пороги под депозит <= $500 (можно будет вынести в config.py позже) ---
ULTRA_MAX_HOURS = 24
ULTRA_MIN_VOL_CEX = 300_000
ULTRA_MIN_VOL_DEX = 500_000

SPIKE_RATIO = 2.0          # x2
SPIKE_MAX_AGE_DAYS = 3     # только первые 3 дня
SPIKE_MIN_BASE_VOL = 50_000  # чтобы не было "x10" из 100$


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


def coin_usd_quote(coin: Dict[str, Any]) -> Dict[str, Any]:
    return (coin.get("quote") or {}).get("USD") or {}


def get_market_pairs(coin: Dict[str, Any]) -> int:
    # В listings обычно есть num_market_pairs
    try:
        return int(coin.get("num_market_pairs") or 0)
    except Exception:
        return 0


def build_keyboard(cmc_url: str, markets_url: str, cmc_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔎 CoinMarketCap", url=cmc_url),
                InlineKeyboardButton("💱 Где купить", url=markets_url),
            ],
            [
                InlineKeyboardButton("⭐ Добавить в отслеживаемые", callback_data=f"track:{cmc_id}"),
            ],
        ]
    )


def build_newcoin_text(
    tag: str,
    coin: Dict[str, Any],
    age: int,
    market_cap: float,
    vol24: float,
    pairs: int,
    urls: Dict[str, str],
) -> str:
    return (
        f"{tag}\n\n"
        f"*{coin.get('name')}* (`{coin.get('symbol')}`)\n"
        f"CMC ID: `{coin.get('id')}`\n"
        f"Slug: `{coin.get('slug')}`\n"
        f"Дата добавления: `{coin.get('date_added')}`\n"
        f"Возраст: *{age}* дн.  |  Пары: *{pairs}*\n\n"
        f"Market Cap: *{fmt_money(market_cap)}*\n"
        f"Volume 24h: *{fmt_money(vol24)}*\n\n"
        f"Ссылки:\n"
        f"• CoinMarketCap: {urls['cmc']}\n"
        f"• Markets: {urls['markets']}"
    )


def build_spike_text(
    coin: Dict[str, Any],
    age: int,
    base_vol: float,
    cur_vol: float,
    urls: Dict[str, str],
) -> str:
    ratio = (cur_vol / base_vol) if base_vol > 0 else 0.0
    return (
        "🔥 *VOLUME SPIKE (вход)*\n\n"
        f"*{coin.get('name')}* (`{coin.get('symbol')}`)\n"
        f"Возраст: *{age}* дн.\n"
        f"Объём 24h: {fmt_money(cur_vol)} (было {fmt_money(base_vol)})\n"
        f"Рост объёма: *x{ratio:.2f}*\n\n"
        "💡 *План под депозит ≤ $500:*\n"
        "• Вход: *$15–25* (3–5%)\n"
        "• TP1: *+30–40%* → забрать тело\n"
        "• Остаток: безубыток\n\n"
        f"• CMC: {urls['cmc']}\n"
        f"• Markets: {urls['markets']}"
    )


def passes_base_filters(coin: Dict[str, Any], max_age_days: int, min_volume_usd: float) -> Optional[Dict[str, Any]]:
    age = age_days(coin.get("date_added", ""))
    if age is None or age > max_age_days:
        return None

    usd = coin_usd_quote(coin)
    market_cap = float(usd.get("market_cap") or 0)
    vol24 = float(usd.get("volume_24h") or 0)
    pct1h = float(usd.get("percent_change_1h") or 0)

    if vol24 < min_volume_usd:
        return None

    slug = (coin.get("slug") or "").strip()
    if not slug:
        return None

    return {
        "age": age,
        "market_cap": market_cap,
        "vol24": vol24,
        "pct1h": pct1h,
        "slug": slug,
        "pairs": get_market_pairs(coin),
    }


def is_ultra_early(metrics: Dict[str, Any]) -> bool:
    # age_days ≤ 0? бывает дробно? у нас int days, поэтому используем часы через days:
    # ultra: age == 0 (в пределах суток) — но CMC может дать age 1 уже на следующий день.
    # Мы считаем ultra если age <= 1 и реально хотим 0–24ч.
    # Упростим: age == 0 ИЛИ (age == 1 и проект добавлен "вчера" поздно) — точнее сделать можно позже.
    # Пока: считаем ultra если age <= 1.
    return metrics["age"] <= 1


def ultra_volume_ok(metrics: Dict[str, Any]) -> bool:
    # У нас нет достоверного определения CEX/DEX на уровне listings.
    # Поэтому используем единый порог: для ultra берём более строгий из двух (DEX).
    return metrics["vol24"] >= ULTRA_MIN_VOL_DEX


def should_spike(
    metrics: Dict[str, Any],
    base_vol: float,
    cur_vol: float,
) -> bool:
    if metrics["age"] > SPIKE_MAX_AGE_DAYS:
        return False
    if base_vol < SPIKE_MIN_BASE_VOL:
        return False
    if base_vol <= 0:
        return False
    if (cur_vol / base_vol) < SPIKE_RATIO:
        return False
    return True


async def scan_once(app: Application, settings: Settings, cmc: CMCClient, sheets: SheetsClient):
    state = load_state()
    seen = seen_ids(state)
    tracked = tracked_ids(state)
    spiked = spike_sent_ids(state)

    # храним последние котировки, чтобы callback ⭐ мог взять базовый объём
    app.bot_data["last_coin_data"] = {}

    coins = cmc.fetch_recent_listings(limit=settings.limit)
    sent_new = 0
    sent_spike = 0

    for coin in coins:
        cid = int(coin.get("id") or 0)
        if not cid:
            continue

        metrics = passes_base_filters(coin, settings.max_age_days, settings.min_volume_usd)
        if not metrics:
            continue

        # сохраним последние данные для callback
        app.bot_data["last_coin_data"][cid] = {
            "vol24": metrics["vol24"],
            "market_cap": metrics["market_cap"],
            "slug": metrics["slug"],
            "name": coin.get("name"),
            "symbol": coin.get("symbol"),
        }

        urls = cmc_urls(metrics["slug"])

        # 1) VOLUME SPIKE (только если ⭐ отслеживаемая)
        if cid in tracked and cid not in spiked:
            watch = get_watch_volume(state, cid)
            if watch:
                base_vol = float(watch.get("base_volume_24h") or 0)
                cur_vol = float(metrics["vol24"] or 0)

                if should_spike(metrics, base_vol, cur_vol):
                    text = build_spike_text(coin, metrics["age"], base_vol, cur_vol, urls)
                    await app.bot.send_message(
                        chat_id=settings.chat_id,
                        text=text,
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True,
                    )
                    mark_spike_sent(state, cid)
                    save_state(state)
                    sent_spike += 1

        # 2) Новая монета (антидубли по seen)
        if cid in seen:
            continue

        mark_seen(state, cid)

        tag = "🆕 *Новая монета обнаружена*"
        if is_ultra_early(metrics) and ultra_volume_ok(metrics) and metrics["pairs"] >= 1:
            tag = "⚡ *ULTRA-EARLY (отбор, не вход)*"

        text = build_newcoin_text(
            tag=tag,
            coin=coin,
            age=metrics["age"],
            market_cap=metrics["market_cap"],
            vol24=metrics["vol24"],
            pairs=metrics["pairs"],
            urls=urls,
        )
        keyboard = build_keyboard(urls["cmc"], urls["markets"], cid)

        # пишем в таблицу листингов как раньше
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
            "status": "NEW" if tag.startswith("🆕") else "ULTRA",
        })

        await app.bot.send_message(
            chat_id=settings.chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=keyboard,
        )
        sent_new += 1

    save_state(state)

    if sent_new:
        await app.bot.send_message(
            chat_id=settings.chat_id,
            text=f"✅ Listings Radar: новых монет: {sent_new}",
        )
    if sent_spike:
        await app.bot.send_message(
            chat_id=settings.chat_id,
            text=f"🔥 Listings Radar: VOLUME SPIKE сигналов: {sent_spike}",
        )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data.startswith("track:"):
        cid = int(data.split(":", 1)[1])

        state = load_state()
        mark_tracked(state, cid)

        # при новом добавлении в отслеживание — сбросим флаг "уже шлали spike"
        clear_spike_sent(state, cid)

        last = (context.application.bot_data.get("last_coin_data") or {}).get(cid) or {}
        base_vol = float(last.get("vol24") or 0)
        save_watch_volume(state, cid, base_vol)

        save_state(state)

        sheets: SheetsClient = context.application.bot_data["sheets"]
        sheets.mark_status(cid, "TRACK")

        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(f"⭐ Добавлено в отслеживаемые: CMC_ID {cid}\nБаза объёма: {fmt_money(base_vol)}")


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
    app.bot_data["last_coin_data"] = {}

    app.add_handler(CallbackQueryHandler(on_callback))

    await app.initialize()
    await app.start()

    await app.bot.send_message(
        chat_id=settings.chat_id,
        text=(
            "📡 *Listings Radar запущен*\n"
            f"• Интервал: {settings.check_interval_min} мин\n"
            f"• Макс. возраст: {settings.max_age_days} дн\n"
            f"• Мин. объём 24h: ${int(settings.min_volume_usd)}\n\n"
            f"⚡ ULTRA: ≤ 24ч и объём ≥ {ULTRA_MIN_VOL_DEX}\n"
            f"🔥 SPIKE: x{SPIKE_RATIO}+ (только ⭐ отслеживаемые)"
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


if __name__ == "__main__":
    asyncio.run(main())
