import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Set, Optional

STATE_FILE = os.getenv("STATE_FILE", "state.json")


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def save_state(state: Dict[str, Any]) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        # на Railway локальное состояние может быть эфемерным,
        # но для текущей сессии всё равно помогает
        pass


def _as_int_set(values) -> Set[int]:
    out: Set[int] = set()
    for v in values or []:
        try:
            out.add(int(v))
        except Exception:
            continue
    return out


# ---------- SEEN (антидубли новых монет) ----------

def seen_ids(state: Dict[str, Any]) -> Set[int]:
    return _as_int_set(state.get("seen_ids"))


def mark_seen(state: Dict[str, Any], cid: int) -> None:
    s = list(seen_ids(state))
    if cid not in s:
        s.append(cid)
    state["seen_ids"] = s


# ---------- TRACKED (⭐ отслеживаемые) ----------

def tracked_ids(state: Dict[str, Any]) -> Set[int]:
    return _as_int_set(state.get("tracked_ids"))


def mark_tracked(state: Dict[str, Any], cid: int) -> None:
    s = list(tracked_ids(state))
    if cid not in s:
        s.append(cid)
    state["tracked_ids"] = s


# ---------- WATCH VOLUME (база объёма для SPIKE) ----------

def save_watch_volume(state: Dict[str, Any], cid: int, base_volume_24h: float) -> None:
    state.setdefault("watch_volume", {})
    state["watch_volume"][str(cid)] = {
        "base_volume_24h": float(base_volume_24h or 0),
        "base_ts": now_iso_utc(),
    }


def get_watch_volume(state: Dict[str, Any], cid: int) -> Optional[Dict[str, Any]]:
    return (state.get("watch_volume") or {}).get(str(cid))


# ---------- SPIKE SENT (чтобы не спамил одним и тем же) ----------

def spike_sent_ids(state: Dict[str, Any]) -> Set[int]:
    return _as_int_set(state.get("spike_sent_ids"))


def mark_spike_sent(state: Dict[str, Any], cid: int) -> None:
    s = list(spike_sent_ids(state))
    if cid not in s:
        s.append(cid)
    state["spike_sent_ids"] = s


def clear_spike_sent(state: Dict[str, Any], cid: int) -> None:
    s = spike_sent_ids(state)
    if cid in s:
        s.remove(cid)
    state["spike_sent_ids"] = list(s)
