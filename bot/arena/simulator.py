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

    def _update_stats(self, stats: StrategyStats, pnl: float) -> None:
        stats.trades += 1
        stats.pnl_sum += pnl
        stats.pnl_sum_sq += pnl * pnl
        if stats.trades > 1:
            mean = stats.pnl_sum / stats.trades
            variance = max(stats.pnl_sum_sq / stats.trades - mean * mean, 1e-6)
            stats.sharpe_ratio = round(mean / math.sqrt(variance), 4)
        else:
            stats.sharpe_ratio = 0.0
        stats.peak_balance = max(stats.peak_balance or stats.balance, stats.balance)
        if stats.peak_balance and stats.peak_balance > 0:
            drawdown = max(0.0, (stats.peak_balance - stats.balance) / stats.peak_balance * 100.0)
            stats.drawdown_pct = round(drawdown, 4)
            stats.max_drawdown_pct = max(stats.max_drawdown_pct, stats.drawdown_pct)
        else:
            stats.drawdown_pct = 0.0

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
            self._update_stats(stats, pnl)
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
