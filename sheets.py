import datetime as dt
import re
from typing import Dict, Any

import gspread
from google.oauth2.service_account import Credentials


def _sheet_id_from_url(url: str) -> str:
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
    if not m:
        raise RuntimeError("Invalid GOOGLE_SHEET_URL")
    return m.group(1)


class SheetsClient:
    def __init__(self, sheet_url: str, service_account_dict: Dict[str, Any], tab_name: str):
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(service_account_dict, scopes=scopes)
        self.gc = gspread.authorize(creds)

        sheet_id = _sheet_id_from_url(sheet_url)
        self.spreadsheet = self.gc.open_by_key(sheet_id)
        self.ws = self._get_or_create_tab(tab_name)
        self._ensure_header()

    def _get_or_create_tab(self, tab_name: str):
        try:
            return self.spreadsheet.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            return self.spreadsheet.add_worksheet(title=tab_name, rows=2000, cols=20)

    def _ensure_header(self) -> None:
        header = [
            "CMC_ID",
            "Detected_At",
            "Symbol",
            "Name",
            "Slug",
            "Date_Added",
            "Age_Days",
            "MarketCap_USD",
            "Volume24h_USD",
            "CMC_URL",
            "Markets_URL",
            "Status",
        ]
        first_row = self.ws.row_values(1)
        if not first_row or first_row[: len(header)] != header:
            self.ws.update("A1:L1", [header])

    def append_listing(self, row: Dict[str, Any]) -> None:
        values = [
            str(row.get("cmc_id", "")),
            row.get("detected_at", ""),
            row.get("symbol", ""),
            row.get("name", ""),
            row.get("slug", ""),
            row.get("date_added", ""),
            str(row.get("age_days", "")),
            str(row.get("market_cap_usd", "")),
            str(row.get("volume24h_usd", "")),
            row.get("cmc_url", ""),
            row.get("markets_url", ""),
            row.get("status", "NEW"),
        ]
        self.ws.append_row(values, value_input_option="USER_ENTERED")

    def mark_status(self, cmc_id: int, status: str) -> bool:
        try:
            cell = self.ws.find(str(cmc_id), in_column=1)
        except gspread.exceptions.CellNotFound:
            return False
        self.ws.update_cell(cell.row, 12, status)
        return True


def now_iso_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
