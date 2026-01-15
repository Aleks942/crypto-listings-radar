import os
from typing import Dict, Any, Tuple


# 0 = не трекать UNVERIFIED (по умолчанию)
# 1 = можно трекать, но помечаем как UNVERIFIED
ALLOW_UNVERIFIED_TRACK = os.getenv("ALLOW_UNVERIFIED_TRACK", "0").strip() == "1"


def _s(x: Any) -> str:
    return (str(x) if x is not None else "").strip()


def is_unverified_token(token: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Возвращает (unverified, reason)
    """
    symbol = _s(token.get("symbol")).upper()
    name = _s(token.get("name"))
    slug = _s(token.get("slug")).lower()

    mcap = float(token.get("market_cap") or 0)
    vol = float(token.get("volume_24h") or 0)

    # 1) домены/URL в имени/slug — частый мусор
    if "." in name or "http" in name.lower() or "www" in name.lower():
        return True, "В названии/описании признаки домена/URL"

    if "." in slug or "http" in slug or "www" in slug:
        return True, "В slug признаки домена/URL"

    # 2) символ с подчёркиванием/странный формат
    if "_" in symbol:
        return True, "Подозрительный symbol (есть _)"

    # 3) market cap = 0 при объёме — часто фейк или некорректные данные
    if mcap == 0 and vol >= 500_000:
        return True, "Market Cap = 0 при высоком объёме"

    # 4) очень длинный тикер — чаще мусор, чем реальный актив
    if len(symbol) >= 12:
        return True, "Слишком длинный symbol"

    return False, "OK"
