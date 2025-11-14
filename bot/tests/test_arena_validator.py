from __future__ import annotations

from bot.arena.models import StrategyProfile, StrategyStats
from bot.arena.validator import validate_strategy


def test_validator_blocks_low_stats():
    profile = StrategyProfile(
        id="strat_x",
        name="Test",
        category="scalp",
        timeframe="1m",
        indicators=[],
        stats=StrategyStats(balance=120.0, goal=150.0, trades=10, sharpe_ratio=0.1, max_drawdown_pct=40.0),
    )
    report = validate_strategy(profile, min_trades=20, min_sharpe=0.2, max_drawdown=30.0)
    assert not report.ok
    assert len(report.reasons) == 3


def test_validator_passes_good_stats():
    profile = StrategyProfile(
        id="strat_ok",
        name="Ok",
        category="scalp",
        timeframe="1m",
        indicators=[],
        stats=StrategyStats(balance=200.0, goal=150.0, trades=80, sharpe_ratio=0.5, max_drawdown_pct=20.0),
    )
    report = validate_strategy(profile, min_trades=50, min_sharpe=0.3, max_drawdown=30.0)
    assert report.ok
