from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class ConfidenceContext:
    volatility: float
    dataset_quality: float
    anomaly_score: float


class DynamicConfidenceGate:
    """Ajusta el umbral mínimo de confianza según volatilidad/anomalías."""

    def __init__(self, base_threshold: float = 0.55, max_threshold: float = 0.7, min_threshold: float = 0.45):
        self.base = base_threshold
        self.max = max_threshold
        self.min = min_threshold

    def compute(self, ctx: ConfidenceContext) -> float:
        threshold = self.base
        if ctx.volatility > 1.5:
            threshold += 0.05
        if ctx.dataset_quality < 0.5:
            threshold += 0.05
        if ctx.anomaly_score > 2.5:
            threshold += 0.05
        if ctx.anomaly_score <= 1.0 and ctx.dataset_quality > 0.8:
            threshold -= 0.03
        return max(self.min, min(self.max, threshold))

    def to_metadata(self, threshold: float) -> Dict[str, float]:
        return {"confidence_gate": threshold}
