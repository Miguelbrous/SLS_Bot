#!/usr/bin/env python3
"""Gestiona el tablero de victorias para estrategias Arena."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.tools import arena_rank


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Actualiza el scoreboard de Arena según los runs más recientes.")
    parser.add_argument("--runs", type=Path, nargs="+", required=True, help="Archivos JSON/JSONL con estrategias.")
    parser.add_argument("--scoreboard", type=Path, default=Path("arena/scoreboard.json"))
    parser.add_argument("--champions", type=Path, default=Path("arena/champions.json"))
    parser.add_argument("--score-threshold", type=float, default=1.15)
    parser.add_argument("--promotion-wins", type=int, default=10)
    parser.add_argument("--top", type=int, default=200, help="Máximo de estrategias guardadas en el scoreboard.")
    parser.add_argument("--min-trades", type=int, default=120)
    parser.add_argument("--max-drawdown", type=float, default=5.0)
    parser.add_argument("--max-drift", type=float, default=0.2)
    parser.add_argument("--target-sharpe", type=float, default=1.6)
    parser.add_argument("--target-calmar", type=float, default=2.2)
    parser.add_argument("--target-profit-factor", type=float, default=2.0)
    parser.add_argument("--target-win-rate", type=float, default=0.58)
    parser.add_argument("--target-drawdown", type=float, default=4.5)
    return parser.parse_args()


def make_rank(namespace: argparse.Namespace, paths: List[Path]) -> Dict[str, List[dict]]:
    args = argparse.Namespace(
        min_trades=namespace.min_trades,
        max_drawdown=namespace.max_drawdown,
        max_drift=namespace.max_drift,
        target_sharpe=namespace.target_sharpe,
        target_calmar=namespace.target_calmar,
        target_profit_factor=namespace.target_profit_factor,
        target_win_rate=namespace.target_win_rate,
        target_drawdown=namespace.target_drawdown,
        json=True,
        top=namespace.top,
        paths=paths,
    )
    return arena_rank.rank_candidates(paths, args)


def prune(scoreboard: dict, top: int) -> dict:
    ordered = sorted(scoreboard.items(), key=lambda kv: (kv[1].get("victories", 0), kv[1].get("last_score", 0)), reverse=True)
    trimmed = dict(ordered[:top])
    return trimmed


def update_scoreboard(namespace: argparse.Namespace, ranking: Dict[str, List[dict]], scoreboard: dict) -> dict:
    updated = dict(scoreboard)
    now = _now()
    for row in ranking.get("accepted") or []:
        if row["score"] < namespace.score_threshold:
            continue
        entry = updated.setdefault(row["name"], {"victories": 0})
        entry["victories"] = entry.get("victories", 0) + 1
        entry["last_score"] = row["score"]
        entry["stats"] = row.get("stats")
        entry["source"] = row.get("source")
        entry["updated_at"] = now
    return prune(updated, namespace.top)


def compute_champions(scoreboard: dict, promotion_wins: int) -> List[dict]:
    champions = []
    for name, data in scoreboard.items():
        wins = data.get("victories", 0)
        if wins >= promotion_wins:
            champions.append({"name": name, "victories": wins, "last_score": data.get("last_score"), "stats": data.get("stats")})
    champions.sort(key=lambda item: (item["victories"], item.get("last_score", 0)), reverse=True)
    return champions


def main() -> None:
    args = build_args()
    paths = [p for p in args.runs if p.exists()]
    if not paths:
        raise SystemExit("No runs provided")
    ranking = make_rank(args, paths)
    scoreboard_path = args.scoreboard
    scoreboard = load_json(scoreboard_path)
    scoreboard = update_scoreboard(args, ranking, scoreboard)
    scoreboard_path.parent.mkdir(parents=True, exist_ok=True)
    scoreboard_path.write_text(json.dumps(scoreboard, ensure_ascii=False, indent=2), encoding="utf-8")

    champions = compute_champions(scoreboard, args.promotion_wins)
    args.champions.parent.mkdir(parents=True, exist_ok=True)
    args.champions.write_text(json.dumps(champions, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Scoreboard actualizado ({len(scoreboard)} estrategias, {len(champions)} champions)")


if __name__ == "__main__":
    main()
