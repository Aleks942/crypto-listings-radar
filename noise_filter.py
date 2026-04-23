import os
import re
from typing import Dict, Any, Tuple
from config import Settings


# 0 = не трекать UNVERIFIED (по умолчанию)
# 1 = можно трекать, но помечаем как UNVERIFIED
ALLOW_UNVERIFIED_TRACK = os.getenv("ALLOW_UNVERIFIED_TRACK", "0").strip() == "1"

# Если хочешь смягчить/ужесточить — меняй тут (или вынесем в env позже)
SUSPICIOUS_TLDS = (".com", ".io", ".net", ".org", ".xyz", ".app", ".site", ".finance", ".ai")
URL_HINTS = ("http://", "https://", "www.")

DOMAIN_REGEX = re.compile(r"\b[a-z0-9-]+\.(com|io|net|org|xyz|app|site|finance|ai)\b", re.IGNORECASE)


def _s(x: Any) -> str:
    return (str(x) if x is not None else "").strip()


def _looks_like_domain(text: str) -> bool:
    t = (text or "").strip().lower()
    if any(h in t for h in URL_HINTS):
        return True
    if DOMAIN_REGEX.search(t):
        return True
    # точка сама по себе НЕ домен (Sport.Fun) — поэтому проверяем только tld
    if any(t.endswith(tld) for tld in SUSPICIOUS_TLDS):
        return True
    return False


def is_unverified_token(token: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Возвращает (unverified, reason)
    """
    symbol = _s(token.get("symbol")).upper()
    name = _s(token.get("name"))
    slug = _s(token.get("slug")).lower()

    usd = (token.get("quote") or {}).get("USD") or {}
    mcap = float(usd.get("market_cap") or 0)
    vol = float(usd.get("volume_24h") or 0)

    # 1) Реальные признаки домена/URL
    if _looks_like_domain(name):
        return True, "В названии признаки URL/домена"

    if _looks_like_domain(slug):
        return True, "В slug признаки URL/домена"

    # 2) symbol с подчёркиванием
    if "_" in symbol:
        return True, "Подозрительный symbol (есть _)"

    # 3) market cap = 0 при высоком объёме
    if mcap == 0 and vol >= 500_000:
        return True, "Market Cap = 0 при высоком объёме"

    # 4) очень длинный тикер
    if len(symbol) >= 12:
        return True, "Слишком длинный symbol"

    return False, "OK"

def is_clean_token(token: Dict[str, Any], settings: Settings) -> Tuple[bool, str]:
    """
    allowed = True -> можно отправлять
    """

    if not settings.clean_mode:
        return True, "CLEAN_MODE OFF"

    name = _s(token.get("name")).lower()
    symbol = _s(token.get("symbol")).upper()

    mcap = float(token.get("market_cap") or 0)
    vol = float(token.get("volume_24h") or 0)
    verified = bool(token.get("is_verified"))

    # 1️⃣ Market Cap (смягчён)
    if mcap > 0 and mcap < 300000:
        return False, "Market Cap ниже 300K"

    # 2️⃣ Объём (смягчён)
    if vol < 100000:
        return False, "Объём ниже 100K"

    # 3️⃣ Явный мусор
    banned_words = [
        "presale",
        "1000x",
        "airdrop scam",
    ]

    for word in banned_words:
        if word in name:
            return False, f"Подозрительное слово: {word}"

    # 4️⃣ Китайские символы (оставим)
    if re.search(r'[\u4e00-\u9fff]', name):
        return False, "Китайские символы"

    # 5️⃣ verified больше НЕ обязателен
    # просто пометка, не бан

    if not verified:
        return True, "EARLY OK (unverified)"

    return True, "CLEAN OK"
