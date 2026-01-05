import datetime as dt
import requests
from typing import Any, Dict, List, Optional

CMC_BASE = "https://pro-api.coinmarketcap.com"


class CMCClient:
    def __init__(self, api_key: str, timeout: int = 20):
        self.api_key = api_key
        self.timeout = timeout

    def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{CMC_BASE}{path}"
        headers = {
            "X-CMC_PRO_API_KEY": self.api_key,
            "Accept": "application/json",
        }
        r = requests.get(url, headers=headers, params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def fetch_recent_listings(self, limit: int = 200) -> List[Dict[str, Any]]:
        data = self._get(
            "/v1/cryptocurrency/listings/latest",
            params={
                "start": 1,
                "limit": limit,
                "convert": "USD",
                "sort": "date_added",
                "sort_dir": "desc",
            },
        )
        return data.get("data", [])


def parse_date_added(date_str: str) -> Optional[dt.datetime]:
    if not date_str:
        return None
    try:
        if date_str.endswith("Z"):
            date_str = date_str.replace("Z", "+00:00")
        return dt.datetime.fromisoformat(date_str)
    except Exception:
        return None


def age_days(date_added_iso: str) -> Optional[int]:
    d = parse_date_added(date_added_iso)
    if not d:
        return None
    now = dt.datetime.now(dt.timezone.utc)
    delta = now - d.astimezone(dt.timezone.utc)
    return max(0, int(delta.total_seconds() // 86400))


def cmc_urls(slug: str) -> Dict[str, str]:
    base = f"https://coinmarketcap.com/currencies/{slug}/"
    return {
        "cmc": base,
        "markets": base + "markets/",
    }
