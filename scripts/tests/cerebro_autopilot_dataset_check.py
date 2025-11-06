#!/usr/bin/env python3
"""CLI para analizar y validar el dataset de experiencias del Cerebro."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lib import cerebro_autopilot_dataset as dataset_lib


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analiza y valida logs/<mode>/cerebro_experience.jsonl")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("logs/test/cerebro_experience.jsonl"),
        help="Ruta al jsonl (default logs/test/cerebro_experience.jsonl)",
    )
    parser.add_argument("--min-rows", type=int, default=200)
    parser.add_argument("--min-win-rate", type=float, default=0.3)
    parser.add_argument("--max-win-rate", type=float, default=0.8)
    parser.add_argument("--min-symbols", type=int, default=1)
    parser.add_argument("--max-age-hours", type=float, default=0.0, help="0 = sin validar antigüedad")
    parser.add_argument("--output-json", help="Escribe el resumen en un archivo JSON")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    dataset = args.dataset.expanduser()
    stats = dataset_lib.analyze_dataset(dataset)
    dataset_lib.ensure_dataset_quality(
        stats,
        min_rows=max(1, args.min_rows),
        min_win_rate=max(0.0, args.min_win_rate),
        max_win_rate=min(1.0, args.max_win_rate),
        min_symbols=max(1, args.min_symbols),
        max_age_hours=max(0.0, args.max_age_hours),
    )
    output = json.dumps(stats.to_dict(), ensure_ascii=False, indent=2)
    print(output)
    if args.output_json:
        Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_json).write_text(output, encoding="utf-8")


if __name__ == "__main__":
    main()
