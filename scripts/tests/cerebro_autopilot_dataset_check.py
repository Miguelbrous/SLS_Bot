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
    parser.add_argument("--min-rows-per-symbol", type=int, default=0, help="Filas mínimas por símbolo (0 = sin validar)")
    parser.add_argument("--max-symbol-share", type=float, default=1.0, help="Máximo porcentaje permitido para el símbolo dominante (1 = sin validar)")
    parser.add_argument("--min-long-rate", type=float, default=0.0, help="Participación mínima de LONG (0 = sin validar)")
    parser.add_argument("--min-short-rate", type=float, default=0.0, help="Participación mínima de SHORT (0 = sin validar)")
    parser.add_argument("--max-invalid-lines", type=int, default=-1, help="Líneas inválidas toleradas (-1 = sin validar)")
    parser.add_argument("--max-zero-rate", type=float, default=-1.0, help="Máximo ratio de pnl=0 aceptado (-1 = sin validar)")
    parser.add_argument("--max-loss-rate", type=float, default=-1.0, help="Máximo ratio de pérdidas aceptado (-1 = sin validar)")
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
        min_rows_per_symbol=args.min_rows_per_symbol or None,
        max_symbol_share=args.max_symbol_share if 0 < args.max_symbol_share < 1 else None,
        min_long_rate=args.min_long_rate or None,
        min_short_rate=args.min_short_rate or None,
        max_invalid_lines=args.max_invalid_lines if args.max_invalid_lines >= 0 else None,
        max_zero_rate=args.max_zero_rate if args.max_zero_rate >= 0 else None,
        max_loss_rate=args.max_loss_rate if args.max_loss_rate >= 0 else None,
    )
    output = json.dumps(stats.to_dict(), ensure_ascii=False, indent=2)
    print(output)
    if args.output_json:
        Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_json).write_text(output, encoding="utf-8")


if __name__ == "__main__":
    main()
