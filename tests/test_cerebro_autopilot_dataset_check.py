from __future__ import annotations

import json
import os
import time
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
    assert stats.zero_rate == pytest.approx(1 / 3, rel=1e-5)
    assert stats.loss_rate == pytest.approx(1 / 3, rel=1e-5)
    assert isinstance(stats.pnl_median, float)
    assert isinstance(stats.pnl_stddev, float)
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


def test_validate_dataset_min_rows_per_symbol(tmp_path):
    dataset = tmp_path / "dataset.jsonl"
    _write_dataset(dataset, [1.0, -1.0, 0.5], symbols=["BTC", "BTC", "ETH"])
    stats = cadc.analyze_dataset(dataset)
    with pytest.raises(cadc.DatasetValidationError):
        cadc.ensure_dataset_quality(
            stats,
            min_rows=3,
            min_win_rate=0.0,
            max_win_rate=1.0,
            min_symbols=1,
            max_age_hours=0,
            min_rows_per_symbol=2,
        )


def test_validate_dataset_max_symbol_share(tmp_path):
    dataset = tmp_path / "dataset.jsonl"
    pnls = [1.0] * 9 + [-0.5]
    symbols = ["BTC"] * 9 + ["ETH"]
    _write_dataset(dataset, pnls, symbols=symbols)
    stats = cadc.analyze_dataset(dataset)
    with pytest.raises(cadc.DatasetValidationError):
        cadc.ensure_dataset_quality(
            stats,
            min_rows=10,
            min_win_rate=0.0,
            max_win_rate=1.0,
            min_symbols=1,
            max_age_hours=0,
            max_symbol_share=0.8,
        )


def test_validate_dataset_min_long_short_rates(tmp_path):
    dataset = tmp_path / "dataset.jsonl"
    rows = []
    for idx in range(20):
        decision = "LONG" if idx < 18 else "SHORT"
        rows.append(json.dumps({"symbol": "BTC", "decision": decision, "pnl": 1, "features": {}}))
    dataset.write_text("\n".join(rows) + "\n", encoding="utf-8")
    stats = cadc.analyze_dataset(dataset)
    with pytest.raises(cadc.DatasetValidationError):
        cadc.ensure_dataset_quality(
            stats,
            min_rows=20,
            min_win_rate=0.0,
            max_win_rate=1.0,
            min_symbols=1,
            max_age_hours=0,
            min_short_rate=0.2,
        )


def test_validate_dataset_max_invalid_lines(tmp_path):
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text('{"symbol":"BTC","decision":"LONG","pnl":1}\ninvalid\n', encoding="utf-8")
    stats = cadc.analyze_dataset(dataset)
    with pytest.raises(cadc.DatasetValidationError):
        cadc.ensure_dataset_quality(
            stats,
            min_rows=1,
            min_win_rate=0.0,
            max_win_rate=1.0,
            min_symbols=1,
            max_age_hours=0,
            max_invalid_lines=0,
        )


def test_validate_dataset_max_zero_rate(tmp_path):
    dataset = tmp_path / "dataset.jsonl"
    rows = [
        json.dumps({"symbol": "BTC", "decision": "LONG", "pnl": 0.0, "features": {}}),
        json.dumps({"symbol": "BTC", "decision": "SHORT", "pnl": 0.0, "features": {}}),
        json.dumps({"symbol": "ETH", "decision": "LONG", "pnl": 1.0, "features": {}}),
    ]
    dataset.write_text("\n".join(rows) + "\n", encoding="utf-8")
    stats = cadc.analyze_dataset(dataset)
    with pytest.raises(cadc.DatasetValidationError):
        cadc.ensure_dataset_quality(
            stats,
            min_rows=3,
            min_win_rate=0.0,
            max_win_rate=1.0,
            min_symbols=1,
            max_age_hours=0,
            max_zero_rate=0.5,
        )


def test_validate_dataset_max_loss_rate(tmp_path):
    dataset = tmp_path / "dataset.jsonl"
    rows = [
        json.dumps({"symbol": "BTC", "decision": "LONG", "pnl": -1.0, "features": {}}),
        json.dumps({"symbol": "BTC", "decision": "LONG", "pnl": -0.5, "features": {}}),
        json.dumps({"symbol": "ETH", "decision": "SHORT", "pnl": 0.2, "features": {}}),
        json.dumps({"symbol": "ETH", "decision": "SHORT", "pnl": -0.1, "features": {}}),
    ]
    dataset.write_text("\n".join(rows) + "\n", encoding="utf-8")
    stats = cadc.analyze_dataset(dataset)
    with pytest.raises(cadc.DatasetValidationError):
        cadc.ensure_dataset_quality(
            stats,
            min_rows=4,
            min_win_rate=0.0,
            max_win_rate=1.0,
            min_symbols=1,
            max_age_hours=0,
            max_loss_rate=0.5,
        )
