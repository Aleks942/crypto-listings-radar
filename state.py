import json
import os
import time
from typing import Dict, Any, Set, Optional

# ==================================================
# BACKEND SWITCH
# ==================================================
STATE_BACKEND = (os.getenv("STATE_BACKEND", "file") or "file").strip().lower()

STATE_DIR = os.getenv("STATE_DIR", ".")
STATE_FILE = os.path.join(STATE_DIR, "state.json")

STATE_SHEET_TAB = (os.getenv("STATE_SHEET_TAB", "State") or "State").strip()
STATE_SHEET_KEY = (os.getenv("STATE_SHEET_KEY", "BOT_STATE_V1") or "BOT_STATE_V1").strip()


# ==================================================
# FILE BACKEND
# ==================================================
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


# ==================================================
# SHEETS BACK
