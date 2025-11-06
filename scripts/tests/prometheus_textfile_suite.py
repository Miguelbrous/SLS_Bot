#!/usr/bin/env python3
"""
Valida en un solo paso los archivos .prom de Cerebro (ingest + autopilot) usando el textfile collector real.

Por defecto busca NODE_EXPORTER_TEXTFILE_DIR o tmp_metrics/textfile, pero puedes pasar --dir manualmente.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.tests.prometheus_textfile_check as textcheck

DEFAULT_DIR = Path(os.getenv("NODE_EXPORTER_TEXTFILE_DIR") or "tmp_metrics/textfile")
DEFAULT_METRICS = {
    "cerebro_ingest": ["cerebro_ingest_success"],
    "cerebro_autopilot": ["cerebro_autopilot_success"],
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke test para los .prom de Cerebro (ingest + autopilot).")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="Directorio base del textfile collector.")
    parser.add_argument(
        "--max-age-minutes",
        type=int,
        default=30,
        help="Antigüedad máxima aceptada para cada archivo (minutos).",
    )
    parser.add_argument("--require-metric", action="append", default=[], help="Métricas extras que deben aparecer.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    base_dir = args.dir.expanduser().resolve()
    files = {
        "cerebro_ingest": base_dir / "cerebro_ingest.prom",
        "cerebro_autopilot": base_dir / "cerebro_autopilot.prom",
    }
    missing = [name for name, path in files.items() if not path.exists()]
    if missing:
        raise SystemExit(
            f"[textfile-suite] No se encontraron los archivos: {', '.join(missing)} en {base_dir}. "
            "Ejecuta scripts/tools/setup_textfile_collector.py primero."
        )
    for name, path in files.items():
        print(f"[textfile-suite] Validando {name}: {path}")
        required = DEFAULT_METRICS.get(name, []) + list(args.require_metric)
        textcheck.validate_file(path, args.max_age_minutes, required)
    print("[textfile-suite] Todos los archivos están listos para Node Exporter.")


if __name__ == "__main__":
    main()
