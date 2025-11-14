#!/usr/bin/env python3
"""
Organiza artefactos generados por el bot moviendo archivos antiguos a un archivo histórico.

Ejemplos:
    python scripts/tools/rotate_artifacts.py --days 14
    python scripts/tools/rotate_artifacts.py --mode test --include models --include logs
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "bot"))

import sls_bot.config_loader as config_loader  # type: ignore  # noqa: E402


ROTATABLE_PATTERNS = {
    "logs": (".json", ".jsonl", ".log", ".txt"),
    "models": (".json",),
}


@dataclass
class RotationTarget:
    name: str
    path: Path


def _iter_files(root: Path, patterns: Sequence[str]) -> Iterable[Path]:
    for entry in root.iterdir():
        if entry.is_dir():
            continue
        if not entry.suffix:
            continue
        if any(entry.name.endswith(pat) for pat in patterns):
            yield entry


def _archive_path(file_path: Path, archive_root: Path) -> Path:
    mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
    dated_root = archive_root / f"{mtime.year}" / f"{mtime.month:02d}"
    dated_root.mkdir(parents=True, exist_ok=True)
    timestamp = mtime.strftime("%Y%m%d")
    return dated_root / f"{file_path.stem}_{timestamp}{file_path.suffix}"


def _should_preserve(file_path: Path) -> bool:
    return file_path.name in {"active_model.json"}


def rotate(target: RotationTarget, *, max_age: timedelta, dry_run: bool) -> List[str]:
    archive_dir = target.path / "archive"
    patterns = ROTATABLE_PATTERNS.get(target.name, ())
    if not target.path.exists():
        return []
    moved: List[str] = []
    cutoff_ts = datetime.now(timezone.utc) - max_age
    for item in _iter_files(target.path, patterns):
        if _should_preserve(item):
            continue
        item_mtime = datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc)
        if item_mtime >= cutoff_ts:
            continue
        destination = _archive_path(item, archive_dir)
        if dry_run:
            moved.append(f"[dry-run] {item} -> {destination}")
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(item), str(destination))
        moved.append(f"{item} -> {destination}")
    return moved


def _repo_root() -> Path:
    if config_loader.CFG_PATH_IN_USE:
        return Path(config_loader.CFG_PATH_IN_USE).resolve().parent.parent
    return Path(__file__).resolve().parents[2]


def _load_mode_paths(mode: str) -> dict:
    original = os.getenv("SLSBOT_MODE")
    os.environ["SLSBOT_MODE"] = mode
    try:
        cfg = config_loader.load_config()
    finally:
        if original is None:
            os.environ.pop("SLSBOT_MODE", None)
        else:
            os.environ["SLSBOT_MODE"] = original
    paths = cfg.get("paths") or {}
    cerebro_cfg = cfg.get("cerebro") or {}

    def _resolve(raw: str | None, fallback: str) -> Path:
        base = _repo_root()
        raw = raw or fallback
        location = Path(raw).expanduser()
        if not location.is_absolute():
            location = (base / location).resolve()
        return location

    logs_dir = _resolve(paths.get("logs_dir"), "./logs")
    models_dir = _resolve(cerebro_cfg.get("models_dir"), f"./models/cerebro/{mode}")
    return {"logs": logs_dir, "models": models_dir}


def main() -> None:
    parser = argparse.ArgumentParser(description="Rota artefactos antiguos de logs/modelos.")
    parser.add_argument("--mode", action="append", help="Modo(s) a procesar. Por defecto procesa todos.")
    parser.add_argument(
        "--include",
        action="append",
        choices=ROTATABLE_PATTERNS.keys(),
        help="Tipo de artefactos a rotar (logs, models).",
    )
    parser.add_argument("--days", type=int, default=7, help="Edad mínima (días) para archivar el archivo.")
    parser.add_argument("--dry-run", action="store_true", help="Muestra acciones sin mover archivos.")
    args = parser.parse_args()

    cfg = config_loader.load_config()
    available_modes = cfg.get("_available_modes") or [cfg.get("_active_mode") or "default"]
    selected_modes = args.mode or available_modes
    includes = args.include or ROTATABLE_PATTERNS.keys()
    max_age = timedelta(days=max(1, args.days))

    report: List[dict] = []
    for mode in selected_modes:
        paths = _load_mode_paths(mode)
        for name in includes:
            if name not in ROTATABLE_PATTERNS:
                continue
            target_path = paths.get(name)
            if not target_path:
                continue
            moved = rotate(RotationTarget(name=name, path=target_path), max_age=max_age, dry_run=args.dry_run)
            report.append({"mode": mode, "target": name, "path": str(target_path), "moved": moved})

    import json

    print(json.dumps({"days": args.days, "dry_run": args.dry_run, "report": report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
