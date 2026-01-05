import json
import os
from dataclasses import dataclass


def _must(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def _opt_int(name: str, default: int) -> int:
    v = os.getenv(name, "").strip()
    return int(v) if v else default


def _opt_float(name: str, default: float) -> float:
    v = os.getenv(name, "").strip()
    return float(v) if v else default


def _opt_str(name: str, default: str) -> str:
    v = os.getenv(name, "").strip()
    return v if v else default


@dataclass(frozen=True)
class Settings:
    bot_token: str
    chat_id: str
    cmc_api_key: str

    google_sheet_url: str
    google_service_account_json: dict

    sheet_tab_name: str
    check_interval_min: int
    limit: int
    max_age_days: int
    min_volume_usd: float

    @staticmethod
    def load() -> "Settings":
        sa_raw = _must("GOOGLE_SERVICE_ACCOUNT_JSON")
        try:
            sa_dict = json.loads(sa_raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                "GOOGLE_SERVICE_ACCOUNT_JSON must be valid JSON (raw text)."
            ) from e

        return Settings(
            bot_token=_must("BOT_TOKEN"),
            chat_id=_must("CHAT_ID"),
            cmc_api_key=_must("CMC_API_KEY"),
            google_sheet_url=_must("GOOGLE_SHEET_URL"),
            google_service_account_json=sa_dict,
            sheet_tab_name=_opt_str("SHEET_TAB_NAME", "Листинги"),
            check_interval_min=_opt_int("CHECK_INTERVAL_MIN", 60),
            limit=_opt_int("CMC_LIMIT", 200),
            max_age_days=_opt_int("MAX_AGE_DAYS", 14),
            min_volume_usd=_opt_float("MIN_VOLUME_USD", 200000.0),
        )
