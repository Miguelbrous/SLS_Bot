from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json

ARENA_DIR = Path(__file__).resolve().parent
CONFIG_PATH = ARENA_DIR / "cup_config.json"


@dataclass
class CupConfig:
    starting_balance: float = 5.0
    initial_goal: float = 100.0
    goal_increment: float = 50.0
    max_active_strategies: int = 200
    cooldown_after_win_minutes: int = 30
    drawdown_stop_pct: float = 20.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CupConfig":
        return cls(**data)


def load_cup_config(path: Path | None = None) -> CupConfig:
    target = path or CONFIG_PATH
    if not target.exists():
        default = CupConfig()
        target.write_text(json.dumps(default.__dict__, indent=2), encoding="utf-8")
        return default
    data = json.loads(target.read_text(encoding="utf-8"))
    return CupConfig.from_dict(data)
