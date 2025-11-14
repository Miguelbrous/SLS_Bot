import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from cerebro.config import CerebroConfig
from cerebro.pipelines import TrainingConfig, TrainingPipeline
from cerebro.versioning import ModelRegistry
import cerebro.service as cerebro_service


def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["python", "-m", "cerebro.train"], returncode=returncode, stdout=stdout, stderr="")


def test_training_pipeline_registers_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    registry = ModelRegistry(models_dir)
    pipeline = TrainingPipeline(registry)

    artifact_path = models_dir / "model_20240101.json"
    artifact_path.write_text("{}", encoding="utf-8")
    payload = {
        "status": "PROMOVIDO",
        "artifact": str(artifact_path),
        "metrics": {"auc": 0.62, "win_rate": 0.58},
        "tag": "synthetic-test",
    }
    monkeypatch.setattr(pipeline, "_run_command", lambda args: _completed(json.dumps(payload)))

    cfg = TrainingConfig(
        python_bin="python",
        mode="test",
        dataset_path=tmp_path / "dataset.jsonl",
        output_dir=models_dir,
    )
    cfg.dataset_path.write_text("{}", encoding="utf-8")
    result = pipeline.offline_training(cfg)

    assert result == str(artifact_path)
    registry_meta = json.loads((models_dir / "registry.json").read_text(encoding="utf-8"))
    assert "synthetic-test" in registry_meta


def test_register_trade_triggers_auto_train(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLS_CEREBRO_AUTO_TRAIN", "1")
    logs_dir = tmp_path / "logs"
    models_dir = tmp_path / "models"
    metrics_dir = logs_dir / "metrics"
    reports_dir = logs_dir / "reports"
    decisions_log = logs_dir / "cerebro_decisions.jsonl"
    experience_log = logs_dir / "cerebro_experience.jsonl"

    cerebro_service.LOGS_DIR = logs_dir
    cerebro_service.MODELS_DIR = models_dir
    cerebro_service.METRICS_DIR = metrics_dir
    cerebro_service.REPORTS_DIR = reports_dir
    cerebro_service.DECISIONS_LOG = decisions_log
    cerebro_service.EXPERIENCE_LOG = experience_log
    logs_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)

    class DummyIngestion:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def warmup(self, *args: Any, **kwargs: Any) -> None:
            return None

        def schedule(self, *args: Any, **kwargs: Any) -> None:
            return None

        def fetch_now(self, *args: Any, **kwargs: Any) -> list[dict]:
            return [{"close": 100.0, "atr": 5.0, "volume": 1000.0}]

        def run_pending(self, *args: Any, **kwargs: Any) -> dict:
            return {}

    monkeypatch.setattr(cerebro_service, "DataIngestionManager", lambda *a, **k: DummyIngestion())

    config = CerebroConfig(
        enabled=True,
        symbols=["BTCUSDT"],
        timeframes=["15m"],
        refresh_seconds=15,
        news_feeds=[],
        auto_train_interval=2,
    )
    cerebro = cerebro_service.Cerebro(config=config)

    triggered = []

    def fake_offline(cfg: TrainingConfig) -> str | None:
        triggered.append(cfg)
        artifact = models_dir / "model_auto.json"
        artifact.write_text("{}", encoding="utf-8")
        return str(artifact)

    monkeypatch.setattr(cerebro.training, "offline_training", fake_offline)

    base_features = {
        "confidence": 0.65,
        "risk_pct": 0.9,
        "leverage": 10.0,
        "news_sentiment": 0.1,
        "session_guard_risk_multiplier": 1.0,
        "memory_win_rate": 0.55,
        "ml_score": 0.6,
        "session_guard_penalty": 0.0,
    }

    cerebro.register_trade(
        symbol="BTCUSDT",
        timeframe="15m",
        pnl=1.5,
        features=base_features,
        decision="LONG",
    )
    assert triggered == []

    cerebro.register_trade(
        symbol="BTCUSDT",
        timeframe="15m",
        pnl=-0.8,
        features=base_features,
        decision="SHORT",
    )
    assert len(triggered) == 1
    assert experience_log.exists()


def test_simulate_sequence_returns_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLS_CEREBRO_AUTO_TRAIN", "0")
    cerebro_service.LOGS_DIR = tmp_path / "logs"
    cerebro_service.MODELS_DIR = tmp_path / "models"
    cerebro_service.METRICS_DIR = cerebro_service.LOGS_DIR / "metrics"
    cerebro_service.REPORTS_DIR = cerebro_service.LOGS_DIR / "reports"
    cerebro_service.DECISIONS_LOG = cerebro_service.LOGS_DIR / "decisions.jsonl"
    cerebro_service.EXPERIENCE_LOG = cerebro_service.LOGS_DIR / "experience.jsonl"
    cerebro_service.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    cerebro_service.MODELS_DIR.mkdir(parents=True, exist_ok=True)

    class DummyIngestion:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def warmup(self, *args: Any, **kwargs: Any) -> None:
            return None

        def schedule(self, *args: Any, **kwargs: Any) -> None:
            return None

        def fetch_now(self, *args: Any, **kwargs: Any) -> list[dict]:
            return []

        def run_pending(self, *args: Any, **kwargs: Any) -> dict:
            return {}

    monkeypatch.setattr(cerebro_service, "DataIngestionManager", lambda *a, **k: DummyIngestion())

    config = CerebroConfig(
        enabled=True,
        symbols=["BTCUSDT"],
        timeframes=["15m"],
        refresh_seconds=15,
        news_feeds=[],
        auto_train_interval=50,
    )
    cerebro = cerebro_service.Cerebro(config=config)

    rows = []
    price = 50000.0
    for i in range(40):
        rows.append({
            "open": price + i,
            "close": price + i + 5,
            "high": price + i + 10,
            "low": price + i - 10,
            "atr": 150.0,
            "volume": 1000 + i * 5,
        })
    cerebro.feature_store.update("BTCUSDT", "15m", rows)
    result = cerebro.simulate_sequence(symbol="BTCUSDT", timeframe="15m", horizon=20)
    assert result["simulation"]["trades"] == 20
    assert result["simulation"]["avg_pnl"] is not None
