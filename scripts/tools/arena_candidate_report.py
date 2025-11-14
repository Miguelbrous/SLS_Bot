#!/usr/bin/env python3
"""Genera un informe con las estrategias candidatas para pruebas en testnet.

Analiza `bot/arena/ranking_latest.json` y filtra por Sharpe, drawdown y trades
para que puedas decidir qué estrategias llevar a testnet antes de promoverlas.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

DEFAULT_RANKING = Path("bot/arena/ranking_latest.json")


def load_ranking(path: Path) -> List[dict]:
    if not path.exists():
        raise FileNotFoundError(f"No existe el ranking en {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Ranking inválido: se esperaba una lista")
    return payload


def render_table(rows: List[dict]) -> str:
    if not rows:
        return "(sin candidatos)"
    headers = ["ID", "Score", "Sharpe", "MaxDD%", "Trades", "Modo"]
    lines = [" | ".join(headers), " | ".join(["---"] * len(headers))]
    for row in rows:
        lines.append(
            " | ".join(
                [
                    row.get("id", "?"),
                    f"{row.get('score', 0):.3f}",
                    f"{row.get('sharpe_ratio', 0):.2f}",
                    f"{row.get('max_drawdown_pct', 0):.1f}",
                    str(row.get("trades", 0)),
                    row.get("mode", "?"),
                ]
            )
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Resume estrategias candidatas para pruebas en testnet")
    parser.add_argument("--ranking", type=Path, default=DEFAULT_RANKING)
    parser.add_argument("--min-sharpe", type=float, default=0.35)
    parser.add_argument("--max-drawdown", type=float, default=35.0)
    parser.add_argument("--min-trades", type=int, default=40)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--mode", help="Filtrar por modo específico (training/race/champion)")
    args = parser.parse_args()

    rows = load_ranking(args.ranking)
    candidates: List[dict] = []
    for row in rows:
        sharpe = float(row.get("sharpe_ratio") or 0.0)
        drawdown = float(row.get("max_drawdown_pct") or row.get("drawdown_pct") or 0.0)
        trades = int(row.get("trades") or 0)
        if sharpe < args.min_sharpe or drawdown > args.max_drawdown or trades < args.min_trades:
            continue
        if args.mode and row.get("mode") != args.mode:
            continue
        candidates.append(row)
        if len(candidates) >= args.top:
            break

    print(render_table(candidates))
    if candidates:
        best = candidates[0]
        print("\nSugerido:")
        print(f"python scripts/ops.py arena promote {best['id']} --min-trades {args.min_trades} --min-sharpe {args.min_sharpe} --max-drawdown {args.max_drawdown}")


if __name__ == "__main__":
    main()
