import asyncio
from typing import Dict, Any, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

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
    get_trade,
    upsert_trade,
    clear_trade,
)

# ===== Параметры под депозит ≤ $500 =====
ULTRA_MIN_VOL = 500_000  # фильтр ultra
SPIKE_RATIO = 2.0        # рост объёма x2
SPIKE_MAX_AGE_DAYS = 3
SPIKE_MIN_BASE_VOL = 50_000

TP1_PCT = 0.35           # +35%
TRAIL_PCT = 0.20         # -20% от хая


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


def fmt_price(x: Optional[float]) -> str:
    if x is None:
        return "—"
    try:
        x = float(x)
    except Exception:
        return "—"
    if x == 0:
        return "—"
    if x < 0.0001:
        return f"${x:.8f}"
    if x < 0.01:
        return f"${x:.6f}"
    if x < 1:
        return f"${x:.4f}"
    return f"${x:.3f}"


def coin_usd_quote(coin: Dict[str, Any]) -> Dict[str, Any]:
    return (coin.get("quote") or {}).get("USD") or {}


def get_market_pairs(coin: Dict[str, Any]) -> int:
    try:
        return int(coin.get("num_market_pairs") or 0)
    except Exception:
        return 0


def cmc_metrics(coin: Dict[str, Any], max_age_days: int, min_volume_usd: float) -> Optional[Dict[str, Any]]:
    age = age_days(coin.get("date_added", ""))
    if age is None or age > max_age_days:
        return None

    usd = coin_usd_quote(coin)
    market_cap = float(usd.get("market_cap") or 0)
    vol24 = float(usd.get("volume_24h") or 0)
    price = float(usd.get("price") or 0)
    pct1h = float(usd.get("percent_change_1h") or 0)

    if vol24 < min_volume_usd:
        return None

    slug = (coin.get("slug") or "").strip()
    if not slug:
        return None

    return {
        "age": int(age),
        "market_cap": market_cap,
        "vol24": vol24,
        "price": price,
        "pct1h": pct1h,
        "slug": slug,
        "pairs": get_market_pairs(coin),
    }


def is_ultra(metrics: Dict[str, Any]) -> bool:
    return metrics["age"] <= 1 and metrics["vol24"] >= ULTRA_MIN_VOL and metrics["pairs"] >= 1


def should_spike(metrics: Dict[str, Any], base_vol: float, cur_vol: float) -> bool:
    if metrics["age"] > SPIKE_MAX_AGE_DAYS:
        return False
    if base_vol <= 0 or base_vol < SPIKE_MIN_BASE_VOL:
        return False
    if (cur_vol / base_vol) < SPIKE_RATIO:
        return False
    # защита от резкого слива (по CMC)
    if metrics["pct1h"] <= -10:
        return False
    return True


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


def build_listing_text(tag: str, coin: Dict[str, Any], m: Dict[str, Any], urls: Dict[str, str]) -> str:
    return (
        f"{tag}\n\n"
        f"*{coin.get('name')}* (`{coin.get('symbol')}`)\n"
        f"CMC ID: `{coin.get('id')}`\n"
        f"Slug: `{coin.get('slug')}`\n"
        f"Дата добавления: `{coin.get('date_added')}`\n"
        f"Возраст: *{m['age']}* дн.  |  Пары: *{m['pairs']}*\n\n"
        f"Цена (CMC): *{fmt_price(m['price'])}*\n"
        f"Market Cap: *{fmt_money(m['market_cap'])}*\n"
        f"Volume 24h: *{fmt_money(m['vol24'])}*\n\n"
        f"Ссылки:\n"
        f"• CoinMarketCap: {urls['cmc']}\n"
        f"• Markets: {urls['markets']}"
    )


def build_spike_text(coin: Dict[str, Any], m: Dict[str, Any], base_vol: float, urls: Dict[str, str]) -> str:
    ratio = (m["vol24"] / base_vol) if base_vol > 0 else 0.0
    return (
        "🔥 *VOLUME SPIKE (точка входа)*\n\n"
        f"*{coin.get('name')}* (`{coin.get('symbol')}`)\n"
        f"Возраст: *{m['age']}* дн.\n"
        f"Цена (CMC): *{fmt_price(m['price'])}*\n"
        f"Объём 24h: {fmt_money(m['vol24'])} (было {fmt_money(base_vol)})\n"
        f"Рост объёма: *x{ratio:.2f}*\n\n"
        "💡 *План (депозит ≤ $500):*\n"
        "• Вход: *$15–25* (3–5%)\n"
        "• TP1: *+30–40%* → забрать тело\n"
        "• Остаток: безубыток + трейл\n\n"
        f"• CMC: {urls['cmc']}\n"
        f"• Markets: {urls['markets']}"
    )


def build_tp1_text(coin: Dict[str, Any], m: Dict[str, Any], entry: float, target: float, urls: Dict[str, str]) -> str:
    return (
        "🟢 *TP1 ДОСТИГНУТ*\n\n"
        f"*{coin.get('name')}* (`{coin.get('symbol')}`)\n"
        f"Вход-референс (CMC на SPIKE): {fmt_price(entry)}\n"
        f"TP1 цель: {fmt_price(target)}\n"
        f"Текущая (CMC): *{fmt_price(m['price'])}*\n\n"
        "✅ Действие:\n"
        "• Зафиксируй *60% позиции* (+30–40%)\n"
        "• Остаток: безубыток\n\n"
        f"• Markets: {urls['markets']}"
    )


def build_trail_text(coin: Dict[str, Any], m: Dict[str, Any], high: float, stop: float, urls: Dict[str, str]) -> str:
    return (
        "🔴 *TRAIL СРАБОТАЛ (выход остатка)*\n\n"
        f"*{coin.get('name')}* (`{coin.get('symbol')}`)\n"
        f"Хай (CMC): {fmt_price(high)}\n"
        f"TRAIL-уровень (-{int(TRAIL_PCT*100)}%): {fmt_price(stop)}\n"
        f"Текущая (CMC): *{fmt_price(m['price'])}*\n\n"
        "✅ Действие:\n"
        "• Закрой остаток позиции\n"
        "• Зафиксируй результат в TRADES\n\n"
        f"• Markets: {urls['markets']}"
    )


async def scan_once(app: Application, settings: Settings, cmc: CMCClient, sheets: SheetsClient):
    state = load_state()
    seen = seen_ids(state)
    tracked = tracked_ids(state)
    spiked = spike_sent_ids(state)

    coins = cmc.fetch_recent_listings(limit=settings.limit)

    # для callback ⭐ — запоминаем последнее значение объёма/цены
    app.bot_data["last_coin_data"] = {}

    sent_new = 0
    sent_spike = 0
    sent_tp1 = 0
    sent_trail = 0

    for coin in coins:
        cid = int(coin.get("id") or 0)
        if not cid:
            continue

        m = cmc_metrics(coin, settings.max_age_days, settings.min_volume_usd)
        if not m:
            continue

        app.bot_data["last_coin_data"][cid] = {
            "vol24": m["vol24"],
            "price": m["price"],
            "slug": m["slug"],
        }

        urls = cmc_urls(m["slug"])

        # ===== A) EXIT/TRAIL мониторинг (только если есть активная "сделка" от SPIKE) =====
        trade = get_trade(state, cid)
        if trade and m["price"] > 0:
            entry = float(trade.get("entry_price") or 0)
            high = float(trade.get("high_price") or entry)
            tp1_sent = bool(trade.get("tp1_sent") or False)
            closed = bool(trade.get("closed") or False)

            if not closed and entry > 0:
                # обновляем хай
                if m["price"] > high:
                    high = m["price"]
                    trade["high_price"] = high

                tp1_target = float(trade.get("tp1_target") or (entry * (1 + TP1_PCT)))
                trail_stop = high * (1 - TRAIL_PCT)

                # TP1 алерт
                if (not tp1_sent) and m["price"] >= tp1_target:
                    await app.bot.send_message(
                        chat_id=settings.chat_id,
                        text=build_tp1_text(coin, m, entry, tp1_target, urls),
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True,
                    )
                    trade["tp1_sent"] = True
                    tp1_sent = True
                    sent_tp1 += 1

                # TRAIL алерт (только после TP1, чтобы не выбивало рано)
                if tp1_sent and m["price"] <= trail_stop:
                    await app.bot.send_message(
                        chat_id=settings.chat_id,
                        text=build_trail_text(coin, m, high, trail_stop, urls),
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True,
                    )
                    trade["closed"] = True
                    sent_trail += 1

                upsert_trade(state, cid, trade)

        # ===== B) VOLUME SPIKE (вход) =====
        if cid in tracked and cid not in spiked:
            watch = get_watch_volume(state, cid)
            if watch:
                base_vol = float(watch.get("base_volume_24h") or 0)
                if should_spike(m, base_vol, m["vol24"]):
                    await app.bot.send_message(
                        chat_id=settings.chat_id,
                        text=build_spike_text(coin, m, base_vol, urls),
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True,
                    )
                    mark_spike_sent(state, cid)
                    save_state(state)
                    sent_spike += 1

                    # Создаём "сделку" для EXIT/TRAIL, если есть цена
                    if m["price"] > 0:
                        entry = m["price"]
                        trade = {
                            "created_at": now_iso_utc(),
                            "entry_price": entry,
                            "high_price": entry,
                            "tp1_target": entry * (1 + TP1_PCT),
                            "tp1_sent": False,
                            "closed": False,
                        }
                        upsert_trade(state, cid, trade)
                        save_state(state)

        # ===== C) Новые монеты (антидубли по seen) =====
        if cid in seen:
            continue

        mark_seen(state, cid)

        tag = "🆕 *Новая монета обнаружена*"
        if is_ultra(m):
            tag = "⚡ *ULTRA-EARLY (отбор, не вход)*"

        text = build_listing_text(tag, coin, m, urls)
        keyboard = build_keyboard(urls["cmc"], urls["markets"], cid)

        sheets.append_listing({
            "cmc_id": cid,
            "detected_at": now_iso_utc(),
            "symbol": coin.get("symbol"),
            "name": coin.get("name"),
            "slug": m["slug"],
            "date_added": coin.get("date_added"),
            "age_days": m["age"],
            "market_cap_usd": m["market_cap"],
            "volume24h_usd": m["vol24"],
            "cmc_url": urls["cmc"],
            "markets_url": urls["markets"],
            "status": "ULTRA" if tag.startswith("⚡") else "NEW",
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
        await app.bot.send_message(chat_id=settings.chat_id, text=f"✅ Listings Radar: новых монет: {sent_new}")
    if sent_spike:
        await app.bot.send_message(chat_id=settings.chat_id, text=f"🔥 Listings Radar: SPIKE сигналов: {sent_spike}")
    if sent_tp1:
        await app.bot.send_message(chat_id=settings.chat_id, text=f"🟢 Listings Radar: TP1 алертов: {sent_tp1}")
    if sent_trail:
        await app.bot.send_message(chat_id=settings.chat_id, text=f"🔴 Listings Radar: TRAIL алертов: {sent_trail}")


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data.startswith("track:"):
        cid = int(data.split(":", 1)[1])

        state = load_state()
        mark_tracked(state, cid)

        # при новом добавлении — разрешим новый SPIKE и сбросим старую сделку
        clear_spike_sent(state, cid)
        clear_trade(state, cid)

        last = (context.application.bot_data.get("last_coin_data") or {}).get(cid) or {}
        base_vol = float(last.get("vol24") or 0)
        save_watch_volume(state, cid, base_vol)

        save_state(state)

        sheets: SheetsClient = context.application.bot_data["sheets"]
        sheets.mark_status(cid, "TRACK")

        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            f"⭐ Добавлено в отслеживаемые: CMC_ID {cid}\nБаза объёма: {fmt_money(base_vol)}"
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
            f"⚡ ULTRA: age≤1, пары≥1, vol≥{ULTRA_MIN_VOL}\n"
            f"🔥 SPIKE: x{SPIKE_RATIO}+ (только ⭐)\n"
            f"🟢 TP1: +{int(TP1_PCT*100)}% (от цены CMC на SPIKE)\n"
            f"🔴 TRAIL: -{int(TRAIL_PCT*100)}% от хая (после TP1)"
        ),
        parse_mode=ParseMode.MARKDOWN,
    )

    while True:
        try:
            await scan_once(app, settings, cmc, sheets)
        except Exception as e:
            await app.bot.send_message(chat_id=settings.chat_id, text=f"❌ Ошибка Listings Radar: {e}")

        await asyncio.sleep(settings.check_interval_min * 60)


if __name__ == "__main__":
    asyncio.run(main())
