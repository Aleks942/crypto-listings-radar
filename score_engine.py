from dataclasses import dataclass
from typing import List


@dataclass
class Candle:
    o: float
    h: float
    l: float
    c: float
    v: float


@dataclass
class Score:
    letter: str   # A / B / C
    points: int   # 0..4
    reason: str


def score_market(candles: List[Candle]) -> Score:
    if len(candles) < 6:
        return Score("C", 0, "Недостаточно свечей")

    vols = [c.v for c in candles]
    ranges = [c.h - c.l for c in candles]

    vol_spike = vols[-1] >= 1.5 * (sum(vols[:-1]) / max(1, len(vols[:-1])))
    range_expand = ranges[-1] >= 1.2 * (sum(ranges[:-1]) / max(1, len(ranges[:-1])))
    close_strong = candles[-1].c > (candles[-1].l + 0.5 * ranges[-1])
    hl_structure = candles[-1].l > candles[-2].l

    points = sum([
        vol_spike,
        range_expand,
        close_strong,
        hl_structure
    ])

    if points == 4:
        return Score("A", points, "Импульс + объём + структура")
    if points == 3:
        return Score("B", points, "Хороший импульс, умеренный риск")
    return Score("C", points, "Слабый сетап")
