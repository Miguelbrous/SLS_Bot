from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
import statistics


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
    pnl_median: float
    pnl_stddev: float
    invalid_lines: int
    file_age_hours: float
    long_rate: float
    short_rate: float
    dominant_symbol: Optional[str]
    dominant_symbol_share: float
    zero_rate: float
    loss_rate: float

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
            "pnl_median": round(self.pnl_median, 6),
            "pnl_stddev": round(self.pnl_stddev, 6),
            "invalid_lines": self.invalid_lines,
            "file_age_hours": round(self.file_age_hours, 3),
            "long_rate": round(self.long_rate, 6),
            "short_rate": round(self.short_rate, 6),
            "dominant_symbol": self.dominant_symbol,
            "dominant_symbol_share": round(self.dominant_symbol_share, 6),
            "zero_rate": round(self.zero_rate, 6),
            "loss_rate": round(self.loss_rate, 6),
        }


def analyze_dataset(path: Path) -> DatasetStats:
    if not path.exists():
        raise DatasetValidationError(f"No existe el dataset en {path}")
    rows = positives = negatives = zeros = invalid_lines = 0
    pnl_total = 0.0
    pnl_min = float("inf")
    pnl_max = float("-inf")
    symbol_counts: Counter[str] = Counter()
    decisions: Counter[str] = Counter()
    pnls: list[float] = []
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
            pnls.append(pnl)
            rows += 1
            symbol_counts[(entry.get("symbol") or "UNKNOWN").upper()] += 1
            decisions[(entry.get("decision") or "UNKNOWN").upper()] += 1
    positive_rate = (positives / rows) if rows else 0.0
    negative_rate = (negatives / rows) if rows else 0.0
    zero_rate = (zeros / rows) if rows else 0.0
    pnl_avg = (pnl_total / rows) if rows else 0.0
    if pnls:
        try:
            pnl_median = float(statistics.median(pnls))
        except statistics.StatisticsError:
            pnl_median = 0.0
        pnl_stddev = float(statistics.pstdev(pnls)) if len(pnls) > 1 else 0.0
    else:
        pnl_median = 0.0
        pnl_stddev = 0.0
    mtime = path.stat().st_mtime
    age_hours = max(0.0, (time.time() - mtime) / 3600.0)
    long_rate = (decisions.get("LONG", 0) / rows) if rows else 0.0
    short_rate = (decisions.get("SHORT", 0) / rows) if rows else 0.0
    dominant_symbol = None
    dominant_symbol_share = 0.0
    if rows and symbol_counts:
        dominant_symbol, dominant_rows = max(symbol_counts.items(), key=lambda item: item[1])
        dominant_symbol_share = dominant_rows / rows
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
        symbol_counts=dict(symbol_counts),
        decision_counts=dict(decisions),
        pnl_avg=pnl_avg,
        pnl_min=pnl_min,
        pnl_max=pnl_max,
        pnl_median=pnl_median,
        pnl_stddev=pnl_stddev,
        invalid_lines=invalid_lines,
        file_age_hours=age_hours,
        long_rate=long_rate,
        short_rate=short_rate,
        dominant_symbol=dominant_symbol,
        dominant_symbol_share=dominant_symbol_share,
        zero_rate=zero_rate,
        loss_rate=negative_rate,
    )


def ensure_dataset_quality(
    stats: DatasetStats,
    *,
    min_rows: int,
    min_win_rate: float,
    max_win_rate: float,
    min_symbols: int,
    max_age_hours: float,
    min_rows_per_symbol: int | None = None,
    max_symbol_share: float | None = None,
    min_long_rate: float | None = None,
    min_short_rate: float | None = None,
    max_invalid_lines: int | None = None,
    max_zero_rate: float | None = None,
    max_loss_rate: float | None = None,
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
    if min_rows_per_symbol:
        under = [symbol for symbol, count in stats.symbol_counts.items() if count < min_rows_per_symbol]
        if under:
            issues.append(
                "Símbolos con pocas filas: "
                + ", ".join(f"{symbol}={stats.symbol_counts[symbol]}" for symbol in under)
            )
    if max_symbol_share is not None and stats.dominant_symbol_share > max_symbol_share:
        issues.append(
            f"El símbolo dominante {stats.dominant_symbol} concentra {stats.dominant_symbol_share:.2%} (> {max_symbol_share:.2%})"
        )
    if min_long_rate is not None and stats.long_rate < min_long_rate:
        issues.append(f"Solo {stats.long_rate:.2%} operaciones LONG (< {min_long_rate:.2%})")
    if min_short_rate is not None and stats.short_rate < min_short_rate:
        issues.append(f"Solo {stats.short_rate:.2%} operaciones SHORT (< {min_short_rate:.2%})")
    if max_age_hours and stats.file_age_hours > max_age_hours:
        issues.append(f"El archivo tiene {stats.file_age_hours:.1f}h (> {max_age_hours}h)")
    if max_invalid_lines is not None:
        if stats.invalid_lines > max_invalid_lines:
            issues.append(f"{stats.invalid_lines} líneas inválidas (> {max_invalid_lines}) en el dataset")
    elif stats.invalid_lines > 0:
        issues.append(f"{stats.invalid_lines} líneas inválidas en el dataset")
    if max_zero_rate is not None and stats.zero_rate > max_zero_rate:
        issues.append(f"El ratio de pnl=0 es {stats.zero_rate:.2%} (> {max_zero_rate:.2%})")
    if max_loss_rate is not None and stats.loss_rate > max_loss_rate:
        issues.append(f"El ratio de pérdidas es {stats.loss_rate:.2%} (> {max_loss_rate:.2%})")
    if issues:
        raise DatasetValidationError("; ".join(issues))
