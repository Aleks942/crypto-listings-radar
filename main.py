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


def build_message(
    coin: Dict[str, Any],
    age: int,
    market_cap: float,
    vol24: float,
    urls: Dict[str, str],
) -> str:
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
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔎 CoinMarketCap", url=cmc_url),
                InlineKeyboardButton("💱 Где ку

