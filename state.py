import json
import os
import time
from typing import Dict, Any, Set


STATE_DIR = os.getenv("STATE_DIR", ".")
STATE_FILE = os.path.join(STATE_DIR, "state.json")


# -----------------------------
# I/O
# -----------------------------

def load_state() -> Dict[str, Any]:
    os.makedirs(STATE_DIR, exist_ok=True)
    if not os.path.exists(STATE_FILE):
        return {
            "seen": {},
            "tracked": {},
            "first_move": {},
            "confirm_light": {},
            "track_debug": {},
        }
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # страховка структуры
        data.setdefault("seen", {})
        data.setdefault("tracked", {})
        data.setdefault("first_move", {})
        data.setdefault("confirm_light", {})
        data.setdefault("track_debug", {})

        return data
    except Exception:
        # если файл битый — начинаем заново, но не падаем
        return {
            "seen": {},
            "tracked": {},
            "first_move": {},
            "confirm_light": {},
            "track_debug": {},
        }


def save_state(state: Dict[str, Any]) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


# -----------------------------
# SEEN (ULTRA)
# -----------------------------

def seen_ids(state: Dict[str, Any]) -> Set[int]:
    return set(int(k) for k in (state.get("seen") or {}).keys())


def mark_seen(state: Dict[str, Any], cid: int) -> None:
    state.setdefault("seen", {})
    state["seen"][str(int(cid))] = {"ts": time.time()}


# -----------------------------
# TRACKED (TRACK MODE)
# -----------------------------

def tracked_ids(state: Dict[str, Any]) -> Set[int]:
    return set(int(k) for k in (state.get("tracked") or {}).keys())


def mark_tracked(state: Dict[str, Any], cid: int) -> None:
    state.setdefault("tracked", {})
    state["tracked"][str(int(cid))] = {"ts": time.time()}


# -----------------------------
# FIRST MOVE anti-dup + cooldown
# -----------------------------

def first_move_sent(state: Dict[str, Any], cid: int) -> bool:
    return str(int(cid)) in (state.get("first_move") or {})


def mark_first_move_sent(state: Dict[str, Any], cid: int, ts: float) -> None:
    state.setdefault("first_move", {})
    state["first_move"][str(int(cid))] = {"ts": float(ts)}


def first_move_cooldown_ok(state: Dict[str, Any], cid: int, cooldown_sec: int) -> bool:
    fm = (state.get("first_move") or {}).get(str(int(cid)))
    if not fm:
        return True
    last_ts = float(fm.get("ts") or 0)
    return (time.time() - last_ts) >= float(cooldown_sec)


# -----------------------------
# CONFIRM-LIGHT anti-dup + cooldown
# -----------------------------

def confirm_light_sent(state: Dict[str, Any], cid: int) -> bool:
    return str(int(cid)) in (state.get("confirm_light") or {})


def mark_confirm_light_sent(state: Dict[str, Any], cid: int, ts: float) -> None:
    state.setdefault("confirm_light", {})
    state["confirm_light"][str(int(cid))] = {"ts": float(ts)}


def confirm_light_cooldown_ok(state: Dict[str, Any], cid: int, cooldown_sec: int) -> bool:
    cl = (state.get("confirm_light") or {}).get(str(int(cid)))
    if not cl:
        return True
    last_ts = float(cl.get("ts") or 0)
    return (time.time() - last_ts) >= float(cooldown_sec)

