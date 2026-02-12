import os
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List

import gspread
from google.oauth2.service_account import Credentials


# ===============================
# helpers
# ===============================
def now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe(fn, retries=3):
    last = None
    for _ in range(retries):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(1.2)
    raise last


# ===============================
# Sheets Client (PRO SAFE VERSION)
# ===============================
class SheetsClient:
    """
    Логика:

    Signals  -> только события (ULTRA / TRACK / FIRST_MOVE / CONFIRM_LIGHT)
    State    -> хранит JSON состояния (одна строка)

    Таблица НЕ будет раздуваться.
    """

    MAX_ROWS = int(os.getenv("SHEETS_MAX_ROWS", "50000"))

    FIXED_HEADERS = [
        "detected_at",
        "cmc_id",
        "symbol",
        "name",
        "age_days",
        "market_cap_usd",
        "volume24h_usd",
        "status",
    ]

    def __init__(self, sheet_url: str, service_account: dict, log_tab_name: str):

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

        creds = Credentials.from_service_account_info(service_account, scopes=scopes)
        self.gc = gspread.authorize(creds)
        self.sh = self.gc.open_by_url(sheet_url)

        self.log_tab_name = log_tab_name or "Signals"
        self.state_tab_name = os.getenv("STATE_SHEET_TAB", "State")
        self.state_key = os.getenv("STATE_SHEET_KEY", "BOT_STATE_V1")

        self.log_tab = self._get_or_create_ws(self.log_tab_name)
        self.state_tab = self._get_or_create_ws(self.state_tab_name)

        self._buffer: List[Dict[str, Any]] = []

        self._ensure_log_headers()
        self._ensure_state_headers()

    # ===============================
    # worksheets
    # ===============================
    def _get_or_create_ws(self, name: str):
        try:
            return self.sh.worksheet(name)
        except Exception:
            return self.sh.add_worksheet(title=name, rows=1000, cols=30)

    def _ensure_log_headers(self):
        row = self.log_tab.row_values(1)
        if row != self.FIXED_HEADERS:
            self.log_tab.clear()
            self.log_tab.append_row(self.FIXED_HEADERS, value_input_option="RAW")

    def _ensure_state_headers(self):
        row = self.state_tab.row_values(1)
        if row != ["key", "json", "updated_at"]:
            self.state_tab.clear()
            self.state_tab.append_row(["key", "json", "updated_at"])

    # ===============================
    # LOG EVENTS
    # ===============================
    def buffer_append(self, row: Dict[str, Any]) -> None:
        self._buffer.append(row)

    def flush(self):

        if not self._buffer:
            return

        values = []

        for r in self._buffer:
            values.append([
                r.get("detected_at", ""),
                r.get("cmc_id", ""),
                r.get("symbol", ""),
                r.get("name", ""),
                r.get("age_days", ""),
                r.get("market_cap_usd", ""),
                r.get("volume24h_usd", ""),
                r.get("status", ""),
            ])

        _safe(lambda: self.log_tab.append_rows(values, value_input_option="RAW"))

        self._buffer.clear()

        # 🔥 авто-защита от переполнения
        self._trim_if_needed()

    def _trim_if_needed(self):

        try:
            total_rows = len(self.log_tab.col_values(1))
        except Exception:
            return

        if total_rows <= self.MAX_ROWS:
            return

        remove_count = total_rows - self.MAX_ROWS

        if remove_count <= 0:
            return

        # удаляем старые строки, оставляя header
        start = 2
        end = 1 + remove_count

        _safe(lambda: self.log_tab.delete_rows(start, end))

    # ===============================
    # STATE JSON
    # ===============================
    def load_state(self) -> Dict[str, Any]:

        col_keys = self.state_tab.col_values(1)

        for idx, k in enumerate(col_keys[1:], start=2):
            if (k or "").strip() == self.state_key:
                row = self.state_tab.row_values(idx)
                raw = row[1] if len(row) > 1 else ""
                try:
                    return json.loads(raw) if raw else {}
                except Exception:
                    return {}

        return {}

    def save_state(self, state: Dict[str, Any]):

        st = dict(state)
        st["__ts"] = float(time.time())

        payload = json.dumps(st, ensure_ascii=False)

        col_keys = self.state_tab.col_values(1)

        for idx, k in enumerate(col_keys[1:], start=2):
            if (k or "").strip() == self.state_key:
                _safe(lambda: self.state_tab.update(
                    f"B{idx}:C{idx}",
                    [[payload, now_iso_utc()]]
                ))
                return

        _safe(lambda: self.state_tab.append_row(
            [self.state_key, payload, now_iso_utc()],
            value_input_option="RAW"
        ))


