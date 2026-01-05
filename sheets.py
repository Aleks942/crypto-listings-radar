from typing import List, Dict, Any
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timezone


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class SheetsClient:
    def __init__(self, sheet_url: str, service_account_json: dict, tab_name: str):
        self.sheet_url = sheet_url
        self.tab_name = tab_name

        creds = Credentials.from_service_account_info(
            service_account_json,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )

        self.service = build("sheets", "v4", credentials=creds)
        self.sheet_id = sheet_url.split("/d/")[1].split("/")[0]

        self._buffer: List[List[Any]] = []

    def buffer_append(self, row: Dict[str, Any]):
        """Складываем строки в память"""
        self._buffer.append([
            row.get("detected_at"),
            row.get("cmc_id"),
            row.get("symbol"),
            row.get("name"),
            row.get("slug"),
            row.get("age_days"),
            row.get("market_cap_usd"),
            row.get("volume24h_usd"),
            row.get("status"),
            row.get("comment", ""),
        ])

    def flush(self):
        """Один запрос в Google Sheets"""
        if not self._buffer:
            return

        body = {
            "values": self._buffer
        }

        self.service.spreadsheets().values().append(
            spreadsheetId=self.sheet_id,
            range=f"{self.tab_name}!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()

        self._buffer.clear()
