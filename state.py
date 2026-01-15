import json
import os
import time
from typing import Dict, Any, Set


STATE_DIR = os.getenv("STATE_DIR", ".")
STATE_FILE = os.path.join(STATE_DIR, "state.json")


def load_state() -> Dict[str, Any]:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: Dict[str, Any]) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


# -------------------------
# SEEN / TRACKED
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


# -------------------------
# FIRST MOVE cooldown / sent
# -------------------------

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


# -------------------------
# CONFIRM LIGHT cooldown / sent
# -------------------------

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


# -------------------------
# STARTUP GUARD (anti-spam "bot started")
# -------------------------

def startup_sent_recent(state: Dict[str, Any], cooldown_sec: int = 3600) -> bool:
    last_ts = float(state.get("startup_ts", 0.0) or 0.0)
    return (time.time() - last_ts) < cooldown_sec


def mark_startup_sent(state: Dict[str, Any]) -> None:
    state["startup_ts"] = float(time.time())

