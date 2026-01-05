import json
import os

BASELINE_PATH = "baseline.json"

def load_baseline():
    if not os.path.exists(BASELINE_PATH):
        return {}
    with open(BASELINE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_baseline(data):
    with open(BASELINE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def ema(prev: float, x: float, alpha: float = 0.25) -> float:
    if not prev:
        return x
    return prev * (1 - alpha) + x * alpha

def update_baseline(baseline: dict, key: str, vol_24h: float) -> float:
    prev = baseline.get(key, 0)
    new = ema(prev, vol_24h)
    baseline[key] = new
    return new
def update_prev_volume(state, cmc_id, volume):
    state.setdefault("prev_volume", {})
    state["prev_volume"][str(cmc_id)] = {
        "volume": volume,
        "ts": time.time()
    }


def get_prev_volume(state, cmc_id):
    return state.get("prev_volume", {}).get(str(cmc_id))
