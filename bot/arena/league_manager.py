from __future__ import annotations

from dataclasses import asdict
from typing import Iterable
import json

from .config import load_cup_config
from .models import StrategyProfile, StrategyStats
from .registry import ArenaRegistry, LEDGER_PATH
from .simulator import MarketSimulator
from .storage import ArenaStorage


class LeagueManager:
    def __init__(self, registry: ArenaRegistry | None = None):
        self.registry = registry or ArenaRegistry()
        self.cfg = load_cup_config()
        self.simulator = MarketSimulator()
        self.storage = ArenaStorage()

    def select_contenders(self) -> list[StrategyProfile]:
        contenders: list[StrategyProfile] = []
        for profile in self.registry.all():
            stats = profile.stats or StrategyStats(balance=self.cfg.starting_balance, goal=self.cfg.initial_goal)
            profile.stats = stats
            if stats.balance >= stats.goal:
                continue
            if profile.mode in ("training", "race") and len(contenders) < self.cfg.max_active_strategies:
                contenders.append(profile)
        return contenders

    def run_tick(self) -> None:
        contenders = self.select_contenders()
        if not contenders:
            return
        ledger_entries = self.simulator.play_batch(contenders)
        for profile in contenders:
            self.registry.upsert(profile)
        self.registry.save()
        self._append_ledger(ledger_entries)

    def _append_ledger(self, entries):
        LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER_PATH.open("a", encoding="utf-8") as fh:
            for entry in entries:
                fh.write(json.dumps(asdict(entry)) + "\n")
        self.storage.append_ledger(entries)

    def promote_winners(self) -> list[StrategyProfile]:
        promoted: list[StrategyProfile] = []
        goal = self.registry.ensure_state().get("current_goal", self.cfg.initial_goal)
        for profile in self.registry.all():
            stats = profile.stats
            if not stats:
                continue
            if stats.balance >= goal and profile.mode != "champion":
                profile.mode = "champion"
                promoted.append(profile)
        if promoted:
            self.registry.update_goal_after_win()
            self.registry.save()
        return promoted
