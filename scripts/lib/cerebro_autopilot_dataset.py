from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict


class DatasetValidationError(RuntimeError):
    """Se lanza cuando el dataset de experiencias no cumple los requisitos."""


@dataclass
class DatasetStats:
    path: Path
    rows: int
    positives: int
    negatives: int
    zeros: int
    positive_rate: float
    negative_rate: float
    symbol_counts: Dict[str, int]
    decision_counts: Dict[str, int]
    pnl_avg: float
    pnl_min: float
    pnl_max: float
    invalid_lines: int
    file_age_hours: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "path": str(self.path),
            "rows": self.rows,
            "positives": self.positives,
            "negatives": self.negatives,
            "zeros": self.zeros,
            "positive_rate": round(self.positive_rate, 6),
            "negative_rate": round(self.negative_rate, 6),
            "symbol_counts": dict(self.symbol_counts),
            "decision_counts": dict(self.decision_counts),
            "pnl_avg": round(self.pnl_avg, 6),
            "pnl_min": self.pnl_min,
            "pnl_max": self.pnl_max,
            "invalid_lines": self.invalid_lines,
            "file_age_hours": round(self.file_age_hours, 3),
        }


def analyze_dataset(path: Path) -> DatasetStats:
    if not path.exists():
        raise DatasetValidationError(f"No existe el dataset en {path}")
    rows = positives = negatives = zeros = invalid_lines = 0
    pnl_total = 0.0
    pnl_min = float("inf")
    pnl_max = float("-inf")
    symbols: Counter[str] = Counter()
    decisions: Counter[str] = Counter()
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                invalid_lines += 1
                continue
            pnl = float(entry.get("pnl") or 0.0)
            pnl_total += pnl
            pnl_min = min(pnl_min, pnl)
            pnl_max = max(pnl_max, pnl)
            if pnl > 0:
                positives += 1
            elif pnl < 0:
                negatives += 1
            else:
                zeros += 1
            rows += 1
            symbols[(entry.get("symbol") or "UNKNOWN").upper()] += 1
            decisions[(entry.get("decision") or "UNKNOWN").upper()] += 1
    positive_rate = (positives / rows) if rows else 0.0
    negative_rate = (negatives / rows) if rows else 0.0
    pnl_avg = (pnl_total / rows) if rows else 0.0
    mtime = path.stat().st_mtime
    age_hours = max(0.0, (time.time() - mtime) / 3600.0)
    if rows == 0:
        pnl_min = 0.0
        pnl_max = 0.0
    return DatasetStats(
        path=path,
        rows=rows,
        positives=positives,
        negatives=negatives,
        zeros=zeros,
        positive_rate=positive_rate,
        negative_rate=negative_rate,
        symbol_counts=dict(symbols),
        decision_counts=dict(decisions),
        pnl_avg=pnl_avg,
        pnl_min=pnl_min,
        pnl_max=pnl_max,
        invalid_lines=invalid_lines,
        file_age_hours=age_hours,
    )


def ensure_dataset_quality(
    stats: DatasetStats,
    *,
    min_rows: int,
    min_win_rate: float,
    max_win_rate: float,
    min_symbols: int,
    max_age_hours: float,
) -> None:
    issues: list[str] = []
    if stats.rows < min_rows:
        issues.append(f"Solo hay {stats.rows} filas (<{min_rows})")
    if stats.positive_rate < min_win_rate:
        issues.append(f"Win rate {stats.positive_rate:.3f} < {min_win_rate}")
    if stats.positive_rate > max_win_rate:
        issues.append(f"Win rate {stats.positive_rate:.3f} > {max_win_rate}")
    symbol_count = len([s for s, count in stats.symbol_counts.items() if count > 0])
    if symbol_count < min_symbols:
        issues.append(f"Hay {symbol_count} símbolos únicos (<{min_symbols})")
    if max_age_hours and stats.file_age_hours > max_age_hours:
        issues.append(f"El archivo tiene {stats.file_age_hours:.1f}h (> {max_age_hours}h)")
    if stats.invalid_lines > 0:
        issues.append(f"{stats.invalid_lines} líneas inválidas en el dataset")
    if issues:
        raise DatasetValidationError("; ".join(issues))
