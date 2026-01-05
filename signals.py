from dataclasses import dataclass
from typing import Optional, Dict

@dataclass
class SignalResult:
    stage: str
    grade: Optional[str]
    score: int
    reasons: list

def compute_score(f: Dict) -> int:
    score = 0

    age = f.get("age_days", 999)
    if age <= 1: score += 25
    elif age <= 3: score += 18
    elif age <= 7: score += 10

    vol = f.get("vol_24h", 0)
    if vol >= 50_000_000: score += 25
    elif vol >= 10_000_000: score += 20
    elif vol >= 1_000_000: score += 12
    elif vol >= 200_000: score += 6

    vr = f.get("vol_ratio", 0)
    if vr >= 3.0: score += 25
    elif vr >= 2.5: score += 22
    elif vr >= 1.8: score += 16

    pc = f.get("price_chg_1h", 0)
    if pc >= 0.20: score += 15
    elif pc >= 0.10: score += 12
    elif pc >= 0.06: score += 8

    pairs = f.get("pairs", 0)
    if pairs >= 30: score += 10
    elif pairs >= 10: score += 7
    elif pairs >= 3: score += 4
    elif pairs >= 1: score += 2

    return min(score, 100)

def classify_signal(f: Dict, cfg: Dict) -> SignalResult:
    reasons = []
    score = compute_score(f)

    stage = "NONE"
    grade = None

    if f["vol_24h"] >= cfg["min_volume_watch"]:
        stage = "WATCH"

    if f["age_days"] <= cfg["ultra_age_days"] and f["vol_24h"] >= cfg["min_volume_ultra"]:
        stage = "ULTRA"
        reasons.append("очень ранний листинг")

    confirm = 0
    if f["vol_ratio"] >= cfg["confirm_volume_ratio"]:
        confirm += 1
        reasons.append("рост объёма")
    if f["price_chg_1h"] >= cfg["confirm_price_chg_1h"]:
        confirm += 1
        reasons.append("рост цены")
    if f["pairs"] >= 3:
        confirm += 1
        reasons.append("есть ликвидность")

    if confirm >= 3:
        stage = "CONFIRM"

    spike = 0
    if f["vol_ratio"] >= cfg["spike_volume_ratio"]:
        spike += 1
    if f["price_chg_1h"] >= cfg["spike_price_chg_1h"]:
        spike += 1
    if f["vol_24h"] >= 5_000_000:
        spike += 1

    if spike >= 2:
        stage = "SPIKE"
        if score >= cfg["grade_A_score"]:
            grade = "A"
        elif score >= cfg["grade_B_score"]:
            grade = "B"
        else:
            grade = "C"

    return SignalResult(stage, grade, score, reasons)
