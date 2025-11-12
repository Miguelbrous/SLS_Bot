#!/usr/bin/env python3
"""Utility to synthesize Arena run files with thousands of strategies."""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path


def _random_name(prefix: str, idx: int) -> str:
    noun = random.choice(
        [
            "apollo",
            "aurora",
            "blade",
            "dune",
            "falcon",
            "halo",
            "ion",
            "nebula",
            "quantum",
            "raptor",
            "vega",
        ]
    )
    return f"{prefix}_{noun}_{idx:04d}"


def synthesize_stats(args: argparse.Namespace) -> dict:
    pnl = random.gauss(args.pnl_mean, args.pnl_std)
    drawdown = abs(random.gauss(args.max_drawdown, 1.5))
    trades = max(40, int(random.gauss(args.trades_mean, args.trades_std)))
    win_rate = _clamp(random.gauss(args.win_rate, 0.08), 0.35, 0.85)
    returns_avg = random.uniform(0.008, 0.05)
    returns_std = max(returns_avg / random.uniform(1.2, 2.5), 0.005)
    gross_profit = max(pnl * random.uniform(2.0, 3.5), pnl * 1.2)
    gross_loss = abs(gross_profit - pnl)
    feature_drift = abs(random.gauss(args.drift_mean, args.drift_std))
    calmar = pnl / max(drawdown, 0.1)
    sharpe = returns_avg / max(returns_std, 0.001)
    profit_factor = gross_profit / max(gross_loss, 1.0)
    return {
        "pnl": round(pnl, 2),
        "max_drawdown": round(drawdown, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "trades": trades,
        "win_rate": round(win_rate, 4),
        "returns_avg": round(returns_avg, 4),
        "returns_std": round(returns_std, 4),
        "feature_drift": round(feature_drift, 4),
        "sharpe": round(sharpe, 4),
        "calmar": round(calmar, 4),
        "profit_factor": round(profit_factor, 4),
    }


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate JSONL runs for Arena/Autopilot")
    parser.add_argument("--count", type=int, default=5000, help="Number of strategies to synthesize")
    parser.add_argument("--output", type=Path, default=Path("arena/runs/arena_5000.jsonl"))
    parser.add_argument("--prefix", type=str, default="scalp")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--pnl-mean", type=float, default=1400.0)
    parser.add_argument("--pnl-std", type=float, default=350.0)
    parser.add_argument("--max-drawdown", type=float, default=4.5)
    parser.add_argument("--trades-mean", type=float, default=210.0)
    parser.add_argument("--trades-std", type=float, default=45.0)
    parser.add_argument("--win-rate", type=float, default=0.58)
    parser.add_argument("--drift-mean", type=float, default=0.08)
    parser.add_argument("--drift-std", type=float, default=0.03)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as fh:
        for idx in range(1, args.count + 1):
            stats = synthesize_stats(args)
            payload = {
                "name": _random_name(args.prefix, idx),
                "symbol": random.choice(["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]),
                "timeframe": random.choice(["1m", "3m", "5m", "15m"]),
                "stats": stats,
                "metadata": {
                    "hold_minutes": random.choice([5, 8, 13, 21, 34]),
                    "entry_model": random.choice(["scalping_v1", "breakout", "mean_revert"]),
                },
            }
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    print(f"Generated {args.count} strategies in {args.output}")


if __name__ == "__main__":
    main()
