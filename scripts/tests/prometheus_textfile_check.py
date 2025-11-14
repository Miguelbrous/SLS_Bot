#!/usr/bin/env python3
"""
Verifica que los archivos .prom del textfile collector existan, estén recientes y contengan las métricas requeridas.

Ejemplo:
  python scripts/tests/prometheus_textfile_check.py --file /var/lib/node_exporter/textfile/cerebro_ingest.prom --require-metric cerebro_ingest_success
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Iterable


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Valida archivos del textfile collector.")
    parser.add_argument("--file", action="append", required=True, help="Ruta al archivo .prom a validar (puedes repetir).")
    parser.add_argument(
        "--max-age-minutes",
        type=int,
        default=30,
        help="Máxima antigüedad permitida para cada archivo (minutos).",
    )
    parser.add_argument(
        "--require-metric",
        action="append",
        default=[],
        help="Nombre de métrica que debe existir en cada archivo (puede repetirse).",
    )
    return parser


def load_metrics(path: Path) -> set[str]:
    metrics: set[str] = set()
    content = path.read_text(encoding="utf-8").splitlines()
    for line in content:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        metric = line.split()[0]
        metrics.add(metric)
    return metrics


def validate_file(path: Path, max_age_minutes: int, required: Iterable[str]) -> None:
    if not path.exists():
        raise SystemExit(f"[textfile-check] No existe {path}")
    age_minutes = (time.time() - path.stat().st_mtime) / 60.0
    if age_minutes > max_age_minutes:
        raise SystemExit(f"[textfile-check] {path} tiene {age_minutes:.1f} min (> {max_age_minutes})")
    metrics = load_metrics(path)
    for metric in required:
        if metric not in metrics:
            raise SystemExit(f"[textfile-check] {path} no contiene la métrica requerida '{metric}'")
    print(f"[textfile-check] {path} OK ({age_minutes:.1f} min)")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    for file_path in args.file:
        validate_file(Path(file_path).expanduser(), args.max_age_minutes, args.require_metric)
    print("[textfile-check] Todos los archivos lucen correctos.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        if exc.code != 0:
            print(str(exc), file=sys.stderr)
        raise
