from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .models import StrategyProfile, StrategyStats


@dataclass
class ValidationReport:
    ok: bool
    reasons: List[str]
    metrics: dict


def validate_strategy(
    profile: StrategyProfile,
    *,
    min_trades: int = 50,
    min_sharpe: float = 0.2,
    max_drawdown: float = 35.0,
) -> ValidationReport:
    stats: StrategyStats | None = profile.stats
    reasons: List[str] = []
    trades = 0
    sharpe = 0.0
    drawdown = 0.0
    if stats:
        trades = stats.trades or (stats.wins + stats.losses)
        sharpe = stats.sharpe_ratio
        drawdown = stats.max_drawdown_pct or stats.drawdown_pct
    else:
        reasons.append("La estrategia no tiene estadísticas registradas.")

    if trades < min_trades:
        reasons.append(f"Se requieren al menos {min_trades} trades, solo hay {trades}.")
    if sharpe < min_sharpe:
        reasons.append(f"Sharpe {sharpe:.2f} es menor al mínimo {min_sharpe}.")
    if drawdown > max_drawdown:
        reasons.append(f"Max drawdown {drawdown:.2f}% supera el permitido ({max_drawdown}%).")

    metrics = {
        "trades": trades,
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": drawdown,
        "wins": stats.wins if stats else 0,
        "losses": stats.losses if stats else 0,
        "balance": stats.balance if stats else None,
        "goal": stats.goal if stats else None,
    }
    return ValidationReport(ok=not reasons, reasons=reasons, metrics=metrics)
