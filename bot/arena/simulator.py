from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List

from ..sls_bot import ia_utils
from .models import StrategyLedgerEntry, StrategyProfile, StrategyStats


@dataclass
class FillResult:
    pnl: float
    balance_after: float
    reason: str


class MarketSimulator:
    """Simulador ligero que comparte un feed de velas con N estrategias."""

    def __init__(self, symbol: str = "BTCUSDT", timeframe: str = "5m"):
        self.symbol = symbol
        self.timeframe = timeframe
        self.last_slice = None

    def refresh_market(self) -> None:
        df, last = ia_utils.latest_slice(self.symbol, self.timeframe, limit=240)
        self.last_slice = (df, last)

    def _calc_pnl(self, profile: StrategyProfile, decision: str) -> float:
        if not self.last_slice:
            self.refresh_market()
        _, last = self.last_slice
        atr = float(last.get("atr", 0.0) or 0.0)
        if atr <= 0:
            atr = float(last.get("close", 0.0)) * 0.004
        edge = random.uniform(0.4, 1.5)
        direction_bias = 1 if decision == "LONG" else -1
        noise = random.uniform(-0.8, 0.8)
        pnl_pct = direction_bias * edge + noise
        pnl = max(min(pnl_pct / 100.0 * last.get("close", 1.0) / 100.0, 5.0), -5.0)
        return pnl

    def play_batch(self, strategies: Iterable[StrategyProfile]) -> List[StrategyLedgerEntry]:
        self.refresh_market()
        ledger: List[StrategyLedgerEntry] = []
        for profile in strategies:
            stats = profile.stats or StrategyStats(balance=5.0, goal=100.0)
            decision = random.choice(["LONG", "SHORT"])
            pnl = self._calc_pnl(profile, decision)
            stats.balance = round(stats.balance + pnl, 4)
            if pnl >= 0:
                stats.wins += 1
            else:
                stats.losses += 1
            stats.drawdown_pct = min(
                100.0,
                max(stats.drawdown_pct, max(0.0, (stats.goal - stats.balance) / stats.goal * 100.0)),
            )
            stats.last_updated = datetime.now(timezone.utc).isoformat()
            profile.stats = stats
            entry = StrategyLedgerEntry(
                strategy_id=profile.id,
                ts=stats.last_updated,
                pnl=pnl,
                balance_after=stats.balance,
                reason=f"sim_{decision.lower()}",
            )
            ledger.append(entry)
        return ledger
