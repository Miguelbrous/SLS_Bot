#!/usr/bin/env python
"""
Promueve el modelo activo del modo de prueba al modo real y reinicia el dataset de pruebas.

Uso:
    python scripts/tools/promote_strategy.py --source-mode test --target-mode real
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[2]


def _metrics_ok(metrics: Dict[str, Any], min_auc: float, min_win: float) -> bool:
    return (metrics.get("auc") or 0.0) >= min_auc and (metrics.get("win_rate") or 0.0) >= min_win


def _load_meta(mode: str) -> Dict[str, Any]:
    meta_path = REPO_ROOT / "models" / "cerebro" / mode / "meta.json"
    if not meta_path.exists():
        raise SystemExit(f"No existe meta.json para el modo '{mode}' en {meta_path}")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _copy_active_model(src_mode: str, dst_mode: str) -> Path:
    src_dir = REPO_ROOT / "models" / "cerebro" / src_mode
    dst_dir = REPO_ROOT / "models" / "cerebro" / dst_mode
    active_src = src_dir / "active_model.json"
    if not active_src.exists():
        raise SystemExit(f"No existe active_model.json en {active_src}")
    dst_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    snapshot_path = dst_dir / f"promoted_{timestamp}.json"
    shutil.copyfile(active_src, snapshot_path)
    shutil.copyfile(active_src, dst_dir / "active_model.json")
    return snapshot_path


def _rotate_experience(mode: str) -> Path | None:
    src_file = REPO_ROOT / "logs" / mode / "cerebro_experience.jsonl"
    if not src_file.exists() or src_file.stat().st_size == 0:
        return None
    archive_dir = src_file.parent / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{src_file.stem}_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.jsonl"
    shutil.move(str(src_file), archive_path)
    src_file.write_text("", encoding="utf-8")
    return archive_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Promueve el modelo entrenado entre modos.")
    parser.add_argument("--source-mode", default="test", help="Modo de origen (normalmente 'test').")
    parser.add_argument("--target-mode", default="real", help="Modo destino (normalmente 'real').")
    parser.add_argument("--min-auc", type=float, default=0.58, help="Umbral mínimo de AUC para promover.")
    parser.add_argument("--min-win-rate", type=float, default=0.55, help="Umbral mínimo de win-rate para promover.")
    parser.add_argument("--skip-dataset-rotation", action="store_true", help="No archiva el dataset del modo de prueba.")
    args = parser.parse_args()

    if args.source_mode == args.target_mode:
        raise SystemExit("source-mode y target-mode deben ser distintos.")

    meta = _load_meta(args.source_mode)
    metrics = meta.get("metrics") or {}
    if not _metrics_ok(metrics, args.min_auc, args.min_win_rate):
        raise SystemExit(
            f"Métricas insuficientes para promover (AUC={metrics.get('auc')}, win_rate={metrics.get('win_rate')})."
        )
    promoted_snapshot = _copy_active_model(args.source_mode, args.target_mode)
    rotation_path = None
    if not args.skip_dataset_rotation:
        rotation_path = _rotate_experience(args.source_mode)

    summary = {
        "status": "promoted",
        "source_mode": args.source_mode,
        "target_mode": args.target_mode,
        "metrics": metrics,
        "artifact": str(promoted_snapshot),
        "experience_archived": str(rotation_path) if rotation_path else None,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
