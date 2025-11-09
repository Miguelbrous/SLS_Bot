#!/usr/bin/env python3
"""
Audita la calidad del dataset de experiencias del Cerebro IA.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from bot.cerebro.dataset_utils import load_rows, summarize_rows  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Valida el dataset cerebro_experience.jsonl.")
    parser.add_argument("--dataset", type=Path, required=True, help="Ruta al dataset jsonl.")
    parser.add_argument("--min-rows", type=int, default=100, help="Mínimo de filas totales.")
    parser.add_argument("--min-win-rate", type=float, default=0.45, help="Win rate mínimo permitido.")
    parser.add_argument("--require-symbols", type=str, default="", help="Lista de símbolos esperados separados por coma.")
    parser.add_argument("--max-dominant-share", type=float, default=0.7, help="Máximo % que puede concentrar un símbolo (0-1).")
    parser.add_argument("--json", action="store_true", help="Imprime el resumen en JSON.")
    return parser.parse_args()


def evaluate(dataset: Path, args: argparse.Namespace) -> int:
    rows = load_rows(dataset)
    summary = summarize_rows(rows)
    violations = []

    if summary["total"] < args.min_rows:
        violations.append(f"Total de filas ({summary['total']}) < min_rows ({args.min_rows})")
    if summary["win_rate"] < args.min_win_rate:
        violations.append(
            f"Win rate {summary['win_rate']:.2f} < min_win_rate {args.min_win_rate:.2f}"
        )
    required = [s.strip().upper() for s in args.require_symbols.split(",") if s.strip()]
    missing = [s for s in required if s not in summary["symbols"]]
    if missing:
        violations.append(f"Faltan símbolos requeridos: {', '.join(missing)}")
    dominant = summary["dominant_symbol_share"]
    if dominant > args.max_dominant_share:
        violations.append(
            f"Un símbolo concentra {dominant:.2f} (> {args.max_dominant_share:.2f})."
        )

    payload = {
        "summary": summary,
        "violations": violations,
        "dataset": str(dataset),
    }
    if args.json or violations:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"Dataset OK: {summary['total']} filas, win_rate={summary['win_rate']:.2f}, símbolos={len(summary['symbols'])}"
        )
    return 1 if violations else 0


def main() -> None:
    args = parse_args()
    sys.exit(evaluate(args.dataset, args))


if __name__ == "__main__":
    main()
