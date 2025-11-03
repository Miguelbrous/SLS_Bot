"""Arena de estrategias: simulación masiva y ranking."""

from .config import CupConfig, load_cup_config
from .models import StrategyProfile, StrategyStats, StrategyLedgerEntry
from .registry import ArenaRegistry
from .ranking import generate_ranking

__all__ = [
    "CupConfig",
    "StrategyProfile",
    "StrategyStats",
    "StrategyLedgerEntry",
    "ArenaRegistry",
    "generate_ranking",
    "load_cup_config",
]
