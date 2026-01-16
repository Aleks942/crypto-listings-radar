import json
import os
import time
from typing import Dict, Any, Set


# ==================================================
# CONFIG
# ==================================================

STATE_DIR = os.getenv("STATE_DIR", ".")
STATE_FILE = os.path.join(STATE_DIR, "state.json")

# FILE (по умолчанию) | SHEETS
STATE_BACKEND = os.getenv("STATE_BACKEND", "FILE").strip().upper()

# Google Sheets state tab
STATE_SHEET_TAB = os.getenv("STATE_SHEET_TAB", "State").strip()       # имя вкладки
STATE_SHEET_KEY = os.getenv("STATE_SHEET_KEY", "BOT_STATE_V1").strip()  # ключ строки


# ==================================================
# DEFAULTS
# ==================================================

def _ensure_defaults(state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(state, dict):
        state = {}

    state.setdefault("seen", [])
    state.setdefault("tracked", [])

    state.setdefault("tracked_meta", {})         # {cid: {ts, symbol, name}}
    state.setdefault("first_move_sent", {})      # {cid: ts}
    state.setdefault("confirm_light_sent", {})   # {cid: ts}
    state.setdefault("startup_ts", 0.0)

    return state


# ==================================================
# FILE BACKEND
# ==================================================

def _file_load() -> Dict[str, Any]:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return _ensure_defaults(json.load(f))
    except Exception:
        return _ensure_defaults({})


def _file_save(state: Dict[str, Any]) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


# ==================================================
# SHEETS BACKEND (gspread)
# ==================================================

_gs_ws = None


def _extract_sheet_id(url: str) -> str:
    # https://docs.google.com/spreadsheets/d/<ID>/edit...
    if "/d/" in url:
        return url.split("/d/")[1].split("/")[0]
    return url.strip()


def _get_ws():
    global _gs_ws
    if _gs_ws is not None:
        return _gs_ws

    import gspread
    from google.oauth2.service_account import Credentials

    sa_raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    sheet_url = os.getenv("GOOGLE_SHEET_URL", "").strip()

    if not sa_raw:
        raise RuntimeError("Missing required env var: GOOGLE_SERVICE_ACCOUNT_JSON")
    if not sheet_url:
        raise RuntimeError("Missing required env var: GOOGLE_SHEET_URL")

    sa_dict = json.loads(sa_raw)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(sa_dict, scopes=scopes)
    gc = gspread.authorize(creds)

    sheet_id = _extract_sheet_id(sheet_url)
    sh = gc.open_by_key(sheet_id)

    ws = sh.worksheet(STATE_SHEET_TAB)

    # убедимся, что есть header key/value
    try:
        values = ws.get_all_values()
        if not values:
            ws.append_row(["key", "value"])
    except Exception:
        pass

    _gs_ws = ws
    return ws


def _sheets_load() -> Dict[str, Any]:
    ws = _get_ws()
    rows = ws.get_all_values()
    if not rows or len(rows) < 2:
        return _ensure_defaults({})

    for r in rows[1:]:
        if not r:
            continue
        k = (r[0] if len(r) > 0 else "").strip()
        v = (r[1] if len(r) > 1 else "").strip()
        if k == STATE_SHEET_KEY and v:
            try:
                return _ensure_defaults(json.loads(v))
            except Exception:
                return _ensure_defaults({})
    return _ensure_defaults({})


def _sheets_save(state: Dict[str, Any]) -> None:
    ws = _get_ws()
    payload = json.dumps(state, ensure_ascii=False)

    rows = ws.get_all_values()
    if not rows:
        ws.append_row(["key", "value"])
        ws.append_row([STATE_SHEET_KEY, payload])
        return

    key_row_idx = None
    for i, r in enumerate(rows[1:], start=2):  # 1-indexed + header
        if r and (r[0].strip() == STATE_SHEET_KEY):
            key_row_idx = i
            break

    if key_row_idx is None:
        ws.append_row([STATE_SHEET_KEY, payload])
    else:
        ws.update_cell(key_row_idx, 2, payload)


# ==================================================
# PUBLIC API
# ==================================================

def load_state() -> Dict[str, Any]:
    if STATE_BACKEND == "SHEETS":
        try:
            return _sheets_load()
        except Exception:
            # если Sheets временно упал — не валим бота
            return _ensure_defaults({})
    return _file_load()


def save_state(state: Dict[str, Any]) -> None:
    state = _ensure_defaults(state)
    state["__ts"] = float(time.time())

    if STATE_BACKEND == "SHEETS":
        try:
            _sheets_save(state)
        except Exception:
            return
    else:
        _file_save(state)


# ==================================================
# SEEN / TRACKED
# ==================================================

def seen_ids(state: Dict[str, Any]) -> Set[int]:
    return set(int(x) for x in state.get("seen", []) if str(x).isdigit())


def mark_seen(state: Dict[str, Any], cid: int) -> None:
    s = set(state.get("seen", []))
    s.add(int(cid))
    state["seen"] = sorted(set(int(x) for x in s))


def tracked_ids(state: Dict[str, Any]) -> Set[int]:
    return set(int(x) for x in state.get("tracked", []) if str(x).isdigit())


def mark_tracked(state: Dict[str, Any], cid: int) -> None:
    s = set(state.get("tracked", []))
    s.add(int(cid))
    state["tracked"] = sorted(set(int(x) for x in s))


# ==================================================
# FIRST MOVE cooldown / sent
# ==================================================

def first_move_sent(state: Dict[str, Any], cid: int) -> bool:
    sent = state.get("first_move_sent", {})
    return str(cid) in sent


def mark_first_move_sent(state: Dict[str, Any], cid: int, ts: float) -> None:
    sent = state.get("first_move_sent", {})
    sent[str(cid)] = float(ts)
    state["first_move_sent"] = sent


def first_move_cooldown_ok(state: Dict[str, Any], cid: int, cooldown_sec: int) -> bool:
    sent = state.get("first_move_sent", {})
    last_ts = float(sent.get(str(cid), 0.0) or 0.0)
    return (time.time() - last_ts) >= cooldown_sec


# ==================================================
# CONFIRM LIGHT cooldown / sent
# ==================================================

def confirm_light_sent(state: Dict[str, Any], cid: int) -> bool:
    sent = state.get("confirm_light_sent", {})
    return str(cid) in sent


def mark_confirm_light_sent(state: Dict[str, Any], cid: int, ts: float) -> None:
    sent = state.get("confirm_light_sent", {})
    sent[str(cid)] = float(ts)
    state["confirm_light_sent"] = sent


def confirm_light_cooldown_ok(state: Dict[str, Any], cid: int, cooldown_sec: int) -> bool:
    sent = state.get("confirm_light_sent", {})
    last_ts = float(sent.get(str(cid), 0.0) or 0.0)
    return (time.time() - last_ts) >= cooldown_sec


# ==================================================
# STARTUP GUARD (anti-spam "bot started")
# ==================================================

def startup_sent_recent(state: Dict[str, Any], cooldown_sec: int = 3600) -> bool:
    last_ts = float(state.get("startup_ts", 0.0) or 0.0)
    return (time.time() - last_ts) < cooldown_sec


def mark_startup_sent(state: Dict[str, Any]) -> None:
    state["startup_ts"] = float(time.time())
    SIGMaSKIBIDU, [16.01.2026 04:26]
❌ Ошибка: [Errno 32] Broken pipe

SIGMaSKIBIDU, [16.01.2026 11:12]
⚡ ULTRA-EARLY

RollX (ROLL)
Возраст: 0 дн
Market Cap: $13,143,434
Volume 24h: $1,913,505

👀 Добавлен в TRACK MODE
⏳ Ждём появления торгов

SIGMaSKIBIDU, [16.01.2026 11:22]
⚡ ULTRA-EARLY

Gas Town (GAS)
Возраст: 0 дн
Market Cap: $0
Volume 24h: $26,233,022

👀 Добавлен в TRACK MODE
⏳ Ждём появления торгов

SIGMaSKIBIDU, [16.01.2026 19:45]
⚡ ULTRA-EARLY

Wrapped Krown (WKROWN)
Возраст: 0 дн
Market Cap: $2,037,499
Volume 24h: $507,201

👀 Добавлен в TRACK MODE
⏳ Ждём появления торгов

SIGMaSKIBIDU, [16.01.2026 19:55]
📡 Listings Radar запущен
Цепочка: ULTRA → TRACK → FIRST MOVE → CONFIRM-LIGHT
SUMMARY: ENTRY + EXIT + VERDICT
DEBUG: OFF

