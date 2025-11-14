from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from .policy import PolicyDecision


@dataclass
class EvaluationBucket:
    total: int = 0
    ml_agreed: int = 0
    heuristic_only: int = 0
    overrides: int = 0

    def register(self, decision: PolicyDecision, ml_score: Optional[float]) -> None:
        self.total += 1
        if ml_score is None:
            self.heuristic_only += 1
        else:
            self.ml_agreed += 1 if decision.metadata.get("action_source") == "ml" else 0
            if decision.metadata.get("ml_override"):
                self.overrides += 1

    def to_dict(self) -> Dict[str, float]:
        return {
            "total": self.total,
            "ml_agreed": self.ml_agreed,
            "heuristic_only": self.heuristic_only,
            "overrides": self.overrides,
        }


class EvaluationTracker:
    """Persistencia ligera para comparar acciones heurísticas vs ML."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self._buckets: Dict[str, EvaluationBucket] = {}
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def register(self, *, symbol: str, timeframe: str, decision: PolicyDecision) -> None:
        key = f"{symbol.upper()}::{timeframe}"
        bucket = self._buckets.setdefault(key, EvaluationBucket())
        ml_score = decision.metadata.get("ml_score")
        bucket.register(decision, ml_score)

    def save(self) -> None:
        payload = {key: bucket.to_dict() for key, bucket in self._buckets.items()}
        path = self.base_dir / "cerebro_evaluation.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def snapshot(self) -> Dict[str, dict]:
        return {key: bucket.to_dict() for key, bucket in self._buckets.items()}
