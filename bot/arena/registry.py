from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

from .models import StrategyProfile, StrategyStats
from .config import ARENA_DIR, load_cup_config

REGISTRY_PATH = ARENA_DIR / "registry.json"
LEDGER_PATH = ARENA_DIR / "ledger.jsonl"
STATE_PATH = ARENA_DIR / "cup_state.json"


class ArenaRegistry:
    def __init__(self, path: Path | None = None):
        self.path = path or REGISTRY_PATH
        self._cache: Dict[str, StrategyProfile] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._cache = {}
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        profiles: Dict[str, StrategyProfile] = {}
        for entry in raw:
            stats = entry.get("stats")
            entry["stats"] = StrategyStats(**stats) if stats else None
            profile = StrategyProfile(**entry)
            profiles[profile.id] = profile
        self._cache = profiles

    def all(self) -> List[StrategyProfile]:
        return list(self._cache.values())

    def get(self, strategy_id: str) -> StrategyProfile | None:
        return self._cache.get(strategy_id)

    def save(self) -> None:
        payload = []
        for profile in self._cache.values():
            data = asdict(profile)
            if profile.stats:
                data["stats"] = asdict(profile.stats)
            payload.append(data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def upsert(self, profile: StrategyProfile) -> None:
        self._cache[profile.id] = profile

    def extend(self, profiles: Iterable[StrategyProfile]) -> None:
        for profile in profiles:
            self.upsert(profile)

    def record_win(self, strategy_id: str, pnl: float) -> None:
        profile = self._cache[strategy_id]
        stats = profile.stats or StrategyStats(balance=5.0, goal=100.0)
        stats.wins += 1
        stats.balance += pnl
        stats.last_updated = datetime.utcnow().isoformat()
        profile.stats = stats
        self._cache[strategy_id] = profile
        self.save()

    def ensure_state(self) -> dict:
        cfg = load_cup_config()
        if not STATE_PATH.exists():
            state = {
                "current_goal": cfg.initial_goal,
                "goal_increment": cfg.goal_increment,
                "wins": 0,
            }
            STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
            return state
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))

    def update_goal_after_win(self) -> float:
        state = self.ensure_state()
        state["wins"] += 1
        state["current_goal"] += state.get("goal_increment", 50.0)
        STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return state["current_goal"]
