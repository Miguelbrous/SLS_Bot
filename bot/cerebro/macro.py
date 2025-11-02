from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Iterable, List


@dataclass
class MacroPulse:
    score: float
    open_interest_bias: float
    funding_bias: float
    whale_pressure: float
    direction: str

    def to_metadata(self) -> dict:
        return {
            "score": self.score,
            "open_interest_bias": self.open_interest_bias,
            "funding_bias": self.funding_bias,
            "whale_pressure": self.whale_pressure,
            "direction": self.direction,
        }


def summarize_macro(rows: Iterable[dict]) -> MacroPulse:
    rows = list(rows or [])
    if not rows:
        return MacroPulse(score=0.0, open_interest_bias=0.0, funding_bias=0.0, whale_pressure=0.0, direction="neutral")

    oi = [float(row.get("open_interest_change_pct") or 0.0) for row in rows]
    funding = [float(row.get("funding_rate") or 0.0) for row in rows]
    whale = [float(row.get("whale_txs") or 0.0) for row in rows]

    oi_bias = mean(oi) if oi else 0.0
    funding_bias = mean(funding) if funding else 0.0
    whale_pressure = mean(whale) if whale else 0.0

    score = 0.0
    score += oi_bias * 0.6
    score += funding_bias * 500  # funding suele ser valores muy pequeños
    score += whale_pressure * 0.05

    direction = "neutral"
    if score > 0.15:
        direction = "bullish"
    elif score < -0.15:
        direction = "bearish"

    return MacroPulse(
        score=score,
        open_interest_bias=oi_bias,
        funding_bias=funding_bias,
        whale_pressure=whale_pressure,
        direction=direction,
    )
