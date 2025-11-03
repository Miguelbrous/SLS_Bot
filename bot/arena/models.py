from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal
from datetime import datetime

ArenaType = Literal["scalp", "intra", "swing", "macro", "quant", "testnet_live"]


@dataclass
class StrategyStats:
    balance: float
    goal: float
    wins: int = 0
    losses: int = 0
    drawdown_pct: float = 0.0
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class StrategyProfile:
    id: str
    name: str
    category: ArenaType
    timeframe: str
    indicators: List[str]
    mode: Literal["draft", "training", "race", "champion"] = "draft"
    engine: Literal["sim", "testnet", "real"] = "sim"
    stats: StrategyStats | None = None
    notes: str | None = None


@dataclass
class StrategyLedgerEntry:
    strategy_id: str
    ts: str
    pnl: float
    balance_after: float
    reason: str
