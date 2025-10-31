from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class AnomalyResult:
    is_anomalous: bool
    score: float
    reason: str | None = None


class AnomalyDetector:
    """Detector simple basado en z-score y umbrales configurables."""

    def __init__(self, *, z_threshold: float = 3.0, min_points: int = 20):
        self.z_threshold = z_threshold
        self.min_points = min_points

    def score_series(self, rows: List[dict], field: str) -> AnomalyResult:
        series = [float(row.get(field, 0.0)) for row in rows if isinstance(row.get(field), (int, float))]
        if len(series) < self.min_points:
            return AnomalyResult(is_anomalous=False, score=0.0, reason="dataset_insuficiente")
        avg = sum(series) / len(series)
        variance = sum((value - avg) ** 2 for value in series) / len(series)
        std = variance ** 0.5 or 1.0
        latest = series[-1]
        z_score = abs(latest - avg) / std
        if z_score >= self.z_threshold:
            return AnomalyResult(is_anomalous=True, score=z_score, reason=f"{field} fuera de rango ({z_score:.2f}σ)")
        return AnomalyResult(is_anomalous=False, score=z_score)

    def evaluate(self, feature_slice: Dict[str, List[dict]]) -> Dict[str, AnomalyResult]:
        results: Dict[str, AnomalyResult] = {}
        for name, rows in feature_slice.items():
            if not rows:
                continue
            result = self.score_series(rows, field="close")
            results[name] = result
        return results
