import json
import os
from typing import Dict, Any, Set

STATE_FILE = "state.json"


def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return {"seen_ids": [], "tracked_ids": []}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # если файл повреждён — начинаем заново, но бот не падает
        return {"seen_ids": [], "tracked_ids": []}


def save_state(state: Dict[str, Any]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def seen_ids(state: Dict[str, Any]) -> Set[int]:
    return set(int(x) for x in state.get("seen_ids", []))


def tracked_ids(state: Dict[str, Any]) -> Set[int]:
    return set(int(x) for x in state.get("tracked_ids", []))


def mark_seen(state: Dict[str, Any], coin_id: int) -> None:
    s = seen_ids(state)
    s.add(int(coin_id))
    state["seen_ids"] = sorted(list(s))


def mark_tracked(state: Dict[str, Any], coin_id: int) -> None:
    t = tracked_ids(state)
    t.add(int(coin_id))
    state["tracked_ids"] = sorted(list(t))
