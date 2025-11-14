from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .versioning import ModelRegistry


@dataclass
class TrainingConfig:
    python_bin: str
    mode: str
    dataset_path: Path
    output_dir: Path
    min_auc: float = 0.6
    min_win_rate: float = 0.55


class TrainingPipeline:
    """Gestiona reentrenos online/offline lanzando cerebro.train."""

    def __init__(self, registry: ModelRegistry):
        self.registry = registry

    def _run_command(self, args: List[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, capture_output=True, text=True, check=False)

    def offline_training(self, cfg: TrainingConfig) -> Optional[str]:
        cmd = [
            cfg.python_bin,
            "-m",
            "cerebro.train",
            "--dataset",
            str(cfg.dataset_path),
            "--output-dir",
            str(cfg.output_dir),
            "--mode",
            cfg.mode,
            "--min-auc",
            str(cfg.min_auc),
            "--min-win-rate",
            str(cfg.min_win_rate),
        ]
        result = self._run_command(cmd)
        if result.returncode != 0:
            return None
        try:
            summary = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return None
        artifact_str = summary.get("artifact_path") or summary.get("artifact") or ""
        if not artifact_str:
            return None
        model_path = Path(artifact_str)
        metrics = summary.get("metrics", {})
        tag = summary.get("tag") or summary.get("version") or model_path.stem
        if model_path.exists():
            self.registry.register(path=model_path, metrics=metrics, tag=tag)
            return str(model_path)
        return None

    def online_update(self, *, experiences_path: Path) -> None:
        if not experiences_path.exists():
            return
        if experiences_path.stat().st_size == 0:
            return
        # Online update placeholder: could be replaced with incremental fit
        # For now we only log the file to indicate it's ready for offline training.
        log_path = experiences_path.parent / "online_updates.log"
        message = f"{experiences_path.name} listo para entrenamiento offline\n"
        log_path.write_text((log_path.read_text(encoding='utf-8') if log_path.exists() else "") + message, encoding="utf-8")


def detect_python_bin() -> str:
    return sys.executable or "python3"
