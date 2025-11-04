from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from .models import StrategyProfile
from .registry import ArenaRegistry
from .config import ARENA_DIR
from .storage import ArenaStorage

RANKING_PATH = ARENA_DIR / "ranking_latest.json"


def _score(profile: StrategyProfile) -> float:
    stats = profile.stats
    if not stats:
        return 0.0
    progress = stats.balance / max(stats.goal, 1.0)
    penalty = stats.drawdown_pct / 100.0
    return max(progress - penalty, 0.0)


def generate_ranking(target: Path | None = None) -> List[Dict[str, object]]:
    registry = ArenaRegistry()
    storage = ArenaStorage()
    latest_balances = {row["strategy_id"]: row for row in storage.top_balances(limit=500)}
    items = []
    for profile in registry.all():
        stats = profile.stats
        latest = latest_balances.get(profile.id)
        balance_override = latest["balance_after"] if latest else None
        row = {
            "id": profile.id,
            "name": profile.name,
            "category": profile.category,
            "mode": profile.mode,
            "engine": profile.engine,
            "score": _score(profile),
            "balance": balance_override if balance_override is not None else (stats.balance if stats else None),
            "goal": stats.goal if stats else None,
            "wins": stats.wins if stats else 0,
            "losses": stats.losses if stats else 0,
            "drawdown_pct": stats.drawdown_pct if stats else 0.0,
        }
        items.append(row)
    items.sort(key=lambda x: x["score"], reverse=True)

    destination = target or RANKING_PATH
    destination.write_text(json.dumps(items[:200], indent=2), encoding="utf-8")
    return items
