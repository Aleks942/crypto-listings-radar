import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, List

import gspread
from google.oauth2.service_account import Credentials


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SheetsClient:
    """
    LOG TAB:
        buffer_append() -> flush() пишет события (ULTRA / TRACK / FIRST_MOVE / CONFIRM_LIGHT)

    STATE TAB:
        хранит JSON state
    """

    # сколько строк держим в основном листе
    MAX_ROWS = 50000
    ARCHIVE_CHUNK = 20000
    ARCHIVE_TAB_NAME = "Radar Archive"

    def __init__(self, sheet_url: str, service_account: dict, log_tab_name: str):
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

        creds = Credentials.from_service_account_info(service_account, scopes=scopes)
        self.gc = gspread.authorize(creds)
        self.sh = self.gc.open_by_url(sheet_url)

        self.log_tab = self._get_or_create_ws(log_tab_name)

        self.state_tab_name = (os.getenv("STATE_SHEET_TAB", "State") or "State").strip()
        self.state_key = (os.getenv("STATE_SHEET_KEY", "BOT_STATE_V1") or "BOT_STATE_V1").strip()
        self.state_tab = self._get_or_create_ws(self.state_tab_name)

        # создаём архивный лист если нет
        self.archive_tab = self._get_or_create_ws(self.ARCHIVE_TAB_NAME)

        self._buffer: List[Dict[str, Any]] = []

        self._ensure_state_headers()

    # ------------------------------------------------
    # helpers
    # ------------------------------------------------
    def _get_or_create_ws(self, name: str):
        try:
            return self.sh.worksheet(name)
        except Exception:
            return self.sh.add_worksheet(title=name, rows=1000, cols=30)

    # ------------------------------------------------
    # LOG (append rows)
    # ------------------------------------------------
    def buffer_append(self, row: Dict[str, Any]) -> None:
        self._buffer.append(row)

    def flush(self) -> None:
        if not self._buffer:
            return

        headers = list(self._buffer[0].keys())

        # ensure header row exists
        existing = self.log_tab.row_values(1)
        if existing != headers:
            self.log_tab.clear()
            self.log_tab.append_row(headers, value_input_option="RAW")

        values = []
        for r in self._buffer:
            values.append([r.get(h, "") for h in headers])

        # ---- ARCHIVE PROTECTION ----
        try:
            current_rows = len(self.log_tab.get_all_values())
            if current_rows > self.MAX_ROWS:
                old = self.log_tab.get_all_values()[1:self.ARCHIVE_CHUNK]

                if old:
                    self.archive_tab.append_rows(old, value_input_option="RAW")
                    self.log_tab.delete_rows(2, self.ARCHIVE_CHUNK)
        except Exception as e:
            print("Archive check error:", e)

        # ---- WRITE NEW DATA ----
        self.log_tab.append_rows(values, value_input_option="RAW")
        self._buffer.clear()

    # ------------------------------------------------
    # STATE (single JSON cell)
    # ------------------------------------------------
    def _ensure_state_headers(self):
        header = self.state_tab.row_values(1)
        if header != ["key", "json", "updated_at"]:
            self.state_tab.clear()
            self.state_tab.append_row(["key", "json", "updated_at"], value_input_option="RAW")

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

    def save_state(self, state: Dict[str, Any]) -> None:
        st = dict(state)
        st["__ts"] = float(datetime.now(timezone.utc).timestamp())

        payload = json.dumps(st, ensure_ascii=False)

        col_keys = self.state_tab.col_values(1)

        for idx, k in enumerate(col_keys[1:], start=2):
            if (k or "").strip() == self.state_key:
                self.state_tab.update(f"B{idx}:C{idx}", [[payload, now_iso_utc()]])
                return

        self.state_tab.append_row([self.state_key, payload, now_iso_utc()], value_input_option="RAW")
