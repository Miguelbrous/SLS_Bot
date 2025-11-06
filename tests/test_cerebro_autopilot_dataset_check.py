from __future__ import annotations

import json
import time
import os
from pathlib import Path

import pytest

from scripts.lib import cerebro_autopilot_dataset as cadc


def _write_dataset(path: Path, pnls: list[float], symbols: list[str] | None = None) -> None:
    symbols = symbols or ["BTCUSDT"] * len(pnls)
    with path.open("w", encoding="utf-8") as fh:
        for pnl, symbol in zip(pnls, symbols, strict=False):
            fh.write(
                json.dumps(
                    {
                        "symbol": symbol,
                        "timeframe": "15m",
                        "decision": "LONG",
                        "pnl": pnl,
                        "features": {},
                    }
                )
                + "\n"
            )


def test_analyze_dataset_counts_rows(tmp_path):
    dataset = tmp_path / "dataset.jsonl"
    _write_dataset(dataset, [1.0, -0.5, 0.0], symbols=["BTCUSDT", "ETHUSDT", "BTCUSDT"])
    stats = cadc.analyze_dataset(dataset)
    assert stats.rows == 3
    assert stats.positives == 1
    assert stats.negatives == 1
    assert stats.zeros == 1
    assert stats.symbol_counts["BTCUSDT"] == 2
    assert stats.decision_counts["LONG"] == 3


def test_validate_dataset_detects_small_sample(tmp_path):
    dataset = tmp_path / "dataset.jsonl"
    _write_dataset(dataset, [0.1])
    stats = cadc.analyze_dataset(dataset)
    with pytest.raises(cadc.DatasetValidationError):
        cadc.ensure_dataset_quality(stats, min_rows=5, min_win_rate=0.0, max_win_rate=1.0, min_symbols=1, max_age_hours=0)


def test_validate_dataset_respects_win_rate_bounds(tmp_path):
    dataset = tmp_path / "dataset.jsonl"
    _write_dataset(dataset, [1.0, 1.0, 1.0])
    stats = cadc.analyze_dataset(dataset)
    with pytest.raises(cadc.DatasetValidationError):
        cadc.ensure_dataset_quality(stats, min_rows=3, min_win_rate=0.1, max_win_rate=0.9, min_symbols=1, max_age_hours=0)


def test_validate_dataset_checks_age(tmp_path):
    dataset = tmp_path / "dataset.jsonl"
    _write_dataset(dataset, [1.0, -1.0, 0.0])
    old_time = time.time() - 3600 * 5
    # Set custom mtime
    os.utime(dataset, (old_time, old_time))
    stats = cadc.analyze_dataset(dataset)
    with pytest.raises(cadc.DatasetValidationError):
        cadc.ensure_dataset_quality(stats, min_rows=3, min_win_rate=0.0, max_win_rate=1.0, min_symbols=1, max_age_hours=1)
