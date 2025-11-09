#!/usr/bin/env python3
"""
Ranking multi-métrica para Arena/Autopilot 2V.

Lee uno o varios archivos (JSON/JSONL) con resultados de backtests/autopilot y
produce una tabla ordenada por score agregando Sharpe, Calmar, Profit Factor,
win rate y drawdown.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rankea candidatos de Arena/Autopilot.")
    parser.add_argument("paths", nargs="+", type=Path, help="Archivos o carpetas con resultados JSON/JSONL.")
    parser.add_argument("--min-trades", type=int, default=50, help="Mínimo de trades para considerar un candidato.")
    parser.add_argument("--max-drawdown", type=float, default=6.0, help="Drawdown (%) máximo permitido.")
    parser.add_argument("--max-drift", type=float, default=0.15, help="Máximo drift permitido (0-1) si existe el campo feature_drift.")
    parser.add_argument("--target-sharpe", type=float, default=1.5)
    parser.add_argument("--target-calmar", type=float, default=2.0)
    parser.add_argument("--target-profit-factor", type=float, default=1.8)
    parser.add_argument("--target-win-rate", type=float, default=0.55)
    parser.add_argument("--target-drawdown", type=float, default=4.0, help="Drawdown óptimo para normalizar.")
    parser.add_argument("--json", action="store_true", help="Imprime la salida completa en JSON.")
    parser.add_argument("--top", type=int, default=5, help="Cantidad de filas a mostrar en modo tabla.")
    return parser.parse_args(list(argv) if argv is not None else None)


def iter_candidates(paths: Iterable[Path]) -> Iterable[dict]:
    for path in paths:
        if path.is_dir():
            for child in sorted(path.iterdir()):
                yield from iter_candidates([child])
            continue
        if path.suffix.lower() == ".jsonl":
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    data.setdefault("_source", str(path))
                    yield data
                except json.JSONDecodeError:
                    continue
        elif path.suffix.lower() == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for item in data:
                        item.setdefault("_source", str(path))
                        yield item
                else:
                    data.setdefault("_source", str(path))
                    yield data
            except json.JSONDecodeError:
                continue


def extract_stats(item: dict) -> Dict[str, float]:
    stats = item.get("stats") or item
    pnl = float(stats.get("pnl") or stats.get("pnl_usd") or 0.0)
    max_dd = abs(float(stats.get("max_drawdown") or stats.get("max_dd_pct") or 0.0))
    gross_profit = float(stats.get("gross_profit") or stats.get("gross_win") or 0.0)
    gross_loss = abs(float(stats.get("gross_loss") or stats.get("gross_loss_abs") or 0.0))
    trades = int(stats.get("trades") or stats.get("num_trades") or 0)
    win_rate = float(stats.get("win_rate") or stats.get("wins") / trades if trades else 0.0)
    returns_avg = float(stats.get("returns_avg") or stats.get("daily_return_avg") or 0.0)
    returns_std = abs(float(stats.get("returns_std") or stats.get("daily_return_std") or 0.0))
    feature_drift = float(stats.get("feature_drift") or item.get("feature_drift") or 0.0)

    sharpe = returns_avg / returns_std if returns_std else 0.0
    calmar = pnl / max_dd if max_dd else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss else math.inf if gross_profit > 0 else 0.0

    return {
        "pnl": pnl,
        "max_drawdown": max_dd,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "trades": trades,
        "win_rate": win_rate,
        "returns_avg": returns_avg,
        "returns_std": returns_std,
        "feature_drift": feature_drift,
        "sharpe": sharpe,
        "calmar": calmar,
        "profit_factor": profit_factor,
    }


def guardrails(stats: Dict[str, float], args: argparse.Namespace) -> List[str]:
    reasons: List[str] = []
    if stats["trades"] < args.min_trades:
        reasons.append(f"min_trades({stats['trades']}<{args.min_trades})")
    if stats["max_drawdown"] > args.max_drawdown:
        reasons.append(f"max_drawdown({stats['max_drawdown']:.2f}>{args.max_drawdown:.2f})")
    if stats["feature_drift"] > args.max_drift:
        reasons.append(f"feature_drift({stats['feature_drift']:.3f}>{args.max_drift:.3f})")
    return reasons


def clamp_ratio(value: float, target: float, cap: float = 2.0) -> float:
    if target <= 0:
        return 0.0
    return max(0.0, min(value / target, cap))


def compute_score(stats: Dict[str, float], args: argparse.Namespace) -> Tuple[float, Dict[str, float]]:
    components = {
        "sharpe": clamp_ratio(stats["sharpe"], args.target_sharpe),
        "calmar": clamp_ratio(stats["calmar"], args.target_calmar),
        "profit_factor": clamp_ratio(stats["profit_factor"], args.target_profit_factor),
        "win_rate": clamp_ratio(stats["win_rate"], args.target_win_rate),
        "drawdown": 1.0 - min(stats["max_drawdown"] / max(args.target_drawdown, 0.01), 1.5),
    }
    weights = {
        "sharpe": 0.3,
        "calmar": 0.25,
        "profit_factor": 0.2,
        "win_rate": 0.15,
        "drawdown": 0.1,
    }
    score = sum(components[key] * weights[key] for key in components)
    return score, components


def rank_candidates(paths: Iterable[Path], args: argparse.Namespace) -> Dict[str, List[dict]]:
    accepted: List[dict] = []
    rejected: List[dict] = []
    for item in iter_candidates(paths):
        name = item.get("name") or item.get("strategy") or item.get("id") or item.get("_source", "unknown")
        stats = extract_stats(item)
        violations = guardrails(stats, args)
        if violations:
            rejected.append({"name": name, "stats": stats, "violations": violations, "source": item.get("_source")})
            continue
        score, comps = compute_score(stats, args)
        accepted.append({
            "name": name,
            "score": round(score, 4),
            "stats": stats,
            "components": {k: round(v, 4) for k, v in comps.items()},
            "source": item.get("_source"),
            "metadata": item.get("metadata"),
        })
    accepted.sort(key=lambda x: x["score"], reverse=True)
    return {"accepted": accepted, "rejected": rejected}


def print_table(accepted: List[dict], top: int) -> None:
    headers = ["#", "Strategy", "Score", "Sharpe", "Calmar", "ProfitF", "Win%", "DD%", "Trades"]
    print(" | ".join(headers))
    print("-" * 80)
    for idx, row in enumerate(accepted[:top], 1):
        metrics = row["stats"]
        comps = row["components"]
        print(
            f"{idx:>2} | {row['name']:<20} | {row['score']:.3f} | "
            f"{metrics['sharpe']:.2f} | {metrics['calmar']:.2f} | {metrics['profit_factor']:.2f} | "
            f"{metrics['win_rate']*100:5.1f}% | {metrics['max_drawdown']:.2f}% | {metrics['trades']}"
        )
        if row.get("source"):
            print(f"    ↳ {row['source']}")
        if comps.get("drawdown") < 0.5:
            print("    ⚠ drawdown componente penalizando")


def main() -> None:
    args = parse_args()
    result = rank_candidates(args.paths, args)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if not result["accepted"]:
            print("No hay candidatos válidos; revisa las violaciones:")
            for rej in result["rejected"]:
                print(f"- {rej['name']}: {', '.join(rej['violations'])}")
        else:
            print_table(result["accepted"], args.top)
            if result["rejected"]:
                print(f"\nDescartados ({len(result['rejected'])}):")
                for rej in result["rejected"]:
                    print(f"- {rej['name']}: {', '.join(rej['violations'])}")


if __name__ == "__main__":
    main()
