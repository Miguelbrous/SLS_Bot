from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


@dataclass
class SimulationResult:
    trades: int
    pnl: float
    avg_pnl: float
    details: List[dict]


class BacktestSimulator:
    """Simulación ultra ligera basada en señales discrecionalmente simples."""

    def simulate(self, *, ohlc: Iterable[dict], decisions: Iterable[str]) -> SimulationResult:
        ohlc_list = list(ohlc)
        decisions_list = list(decisions)
        trades = min(len(ohlc_list), len(decisions_list))
        details: List[dict] = []
        pnl = 0.0
        for idx in range(trades):
            candle = ohlc_list[idx]
            decision = decisions_list[idx]
            open_price = float(candle.get("open", 0.0))
            close_price = float(candle.get("close", open_price))
            if decision == "LONG":
                trade_pnl = close_price - open_price
            elif decision == "SHORT":
                trade_pnl = open_price - close_price
            else:
                trade_pnl = 0.0
            pnl += trade_pnl
            details.append({"decision": decision, "open": open_price, "close": close_price, "pnl": trade_pnl})
        avg = pnl / trades if trades else 0.0
        return SimulationResult(trades=trades, pnl=pnl, avg_pnl=avg, details=details)
