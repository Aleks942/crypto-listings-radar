# state.py
import json
import os
import time
from typing import Dict, Any, Set, Optional


# =========================
# Backend selection
# =========================
# STATE_BACKEND: "sheets" | "file"
STATE_BACKEND = (os.getenv("STATE_BACKEND", "file") or "file").strip().lower()

# File backend
STATE_DIR = os.getenv("STATE_DIR", ".")
STATE_FILE = os.path.join(STATE_DIR, "state.json")

# Sheets backend
STATE_SHEET_TAB = (os.getenv("STATE_SHEET_TAB", "State") or "State").strip()
STATE_SHEET_KEY = (os.getenv("STATE_SHEET_KEY", "BOT_STATE_V1") or "BOT_STATE_V1").strip()

# Обычно это URL твоей таблицы (как раньше)
GOOGLE_SHEET_URL = (os.getenv("GOOGLE_SHEET_URL", "") or "").strip()
GOOGLE_SERVICE_ACCOUNT_JSON = (os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "") or "").strip()


# =========================
# Helpers (Sheets)
# =========================
def _sheets_enabled() -> bool:
    return (
        STATE_BACKEND == "sheets"
        and bool(GOOGLE_SHEET_URL)
        and bool(GOOGLE_SERVICE_ACCOUNT_JSON)
        and bool(STATE_SHEET_TAB)
        and bool(STATE_SHEET_KEY)
    )


def _get_gspread_client():
    # импортируем только если реально используем, чтобы не ломать file-backend
    import gspread
    from google.oauth2.service_account import Credentials

    sa_dict = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(sa_dict, scopes=scopes)
    return gspread.authorize(creds)


def _open_state_sheet():
    gc = _get_gspread_client()
    sh = gc.open_by_url(GOOGLE_SHEET_URL)
    ws = sh.worksheet(STATE_SHEET_TAB)
    return ws


def _ensure_state_header(ws):
    """
    Ожидаем простую табличку:
    A: key
    B: json
    """
    try:
        row1 = ws.row_values(1)
    except Exception:
        row1 = []

    if len(row1) < 2 or (row1[0].strip().lower() != "key" or row1[1].strip().lower() != "json"):
        ws.update("A1:B1", [["key", "json"]])


def _find_row_by_key(ws, key: str) -> Optional[int]:
    """
    Возвращает номер строки (1-based) для данного key, либо None.
    """
    # читаем колонку A целиком (может быть чуть тяжелее, но надёжно)
    col = ws.col_values(1)  # A
    for idx, v in enumerate(col, start=1):
        if (v or "").strip() == key:
            return idx
    return None


def _sheets_load_state() -> Dict[str, Any]:
    ws = _open_state_sheet()
    _ensure_state_header(ws)

    r = _find_row_by_key(ws, STATE_SHEET_KEY)
    if not r:
        return {}

    # json лежит в колонке B
    raw = ws.cell(r, 2).value or ""
    raw = raw.strip()
    if not raw:
        return {}

    try:
        return json.loads(raw)
    except Exception:
        # если кто-то случайно руками испортил JSON — не падаем, просто сбрасываем
        return {}


def _sheets_save_state(state: Dict[str, Any]) -> None:
    ws = _open_state_sheet()
    _ensure_state_header(ws)

    r = _find_row_by_key(ws, STATE_SHEET_KEY)
    payload = json.dumps(state, ensure_ascii=False)

    if not r:
        # добавляем новую строку
        ws.append_row([STATE_SHEET_KEY, payload], value_input_option="RAW")
    else:
        ws.update_cell(r, 2, payload)


# =========================
# Helpers (File)
# =========================
def _file_load_state() -> Dict[str, Any]:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _file_save_state(state: Dict[str, Any]) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


# =========================
# Public API (used by main.py)
# =========================
def load_state() -> Dict[str, Any]:
    """
    Единственная точка входа: main.py делает from state import load_state
    """
    if _sheets_enabled():
        return _sheets_load_state()
    return _file_load_state()


def save_state(state: Dict[str, Any]) -> None:
    """
    Единственная точка входа: main.py делает from state import save_state
    """
    # добавим timestamp чтобы понимать, что state реально обновляется
    state["__ts"] = float(time.time())
    if _sheets_enabled():
        return _sheets_save_state(state)
    return _file_save_state(state)


# -------------------------
# SEEN / WATCH / TRACKED
# -------------------------
def seen_ids(state: Dict[str, Any]) -> Set[int]:
    return set(state.get("seen", []))


def mark_seen(state: Dict[str, Any], cid: int) -> None:
    s = set(state.get("seen", []))
    s.add(int(cid))
    state["seen"] = sorted(s)


def tracked_ids(state: Dict[str, Any]) -> Set[int]:
    return set(state.get("tracked", []))


def mark_tracked(state: Dict[str, Any], cid: int) -> None:
    s = set(state.get("tracked", []))
    s.add(int(cid))
    state["tracked"] = sorted(s)


def watch_ids(state: Dict[str, Any]) -> Set[int]:
    return set(state.get("watch", []))


def mark_watch(state: Dict[str, Any], cid: int) -> None:
    s = set(state.get("watch", []))
    s.add(int(cid))
    state["watch"] = sorted(s)


def unmark_watch(state: Dict[str, Any], cid: int) -> None:
    s = set(state.get("watch", []))
    s.discard(int(cid))
    state["watch"] = sorted(s)


# -------------------------
# FIRST MOVE cooldown / sent
# -------------------------
def first_move_sent(state: Dict[str, Any], cid: int) -> bool:
    sent = state.get("first_move_sent", {}) or {}
    return str(cid) in sent


def mark_first_move_sent(state: Dict[str, Any], cid: int, ts: float) -> None:
    sent = state.get("first_move_sent", {}) or {}
    sent[str(cid)] = float(ts)
    state["first_move_sent"] = sent


def first_move_cooldown_ok(state: Dict[str, Any], cid: int, cooldown_sec: int) -> bool:
    sent = state.get("first_move_sent", {}) or {}
    last_ts = float(sent.get(str(cid), 0.0) or 0.0)
    return (time.time() - last_ts) >= cooldown_sec


# -------------------------
# CONFIRM LIGHT cooldown / sent
# -------------------------
def confirm_light_sent(state: Dict[str, Any], cid: int) -> bool:
    sent = state.get("confirm_light_sent", {}) or {}
    return str(cid) in sent


def mark_confirm_light_sent(state: Dict[str, Any], cid: int, ts: float) -> None:
    sent = state.get("confirm_light_sent", {}) or {}
    sent[str(cid)] = float(ts)
    state["confirm_light_sent"] = sent


def confirm_light_cooldown_ok(state: Dict[str, Any], cid: int, cooldown_sec: int) -> bool:
    sent = state.get("confirm_light_sent", {}) or {}
    last_ts = float(sent.get(str(cid), 0.0) or 0.0)
    return (time.time() - last_ts) >= cooldown_sec


# -------------------------
# STARTUP GUARD (anti-spam "bot started")
# -------------------------
def startup_sent_recent(state: Dict[str, Any], cooldown_sec: int = 3600) -> bool:
    last_ts = float(state.get("startup_ts", 0.0) or 0.0)
    return (time.time() - last_ts) < cooldown_sec


def mark_startup_sent(state: Dict[str, Any]) -> None:
    state["startup_ts"] = float(time.time())

