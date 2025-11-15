from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scripts.lib.demo_learning import (
    ActionPlan,
    DemoDecision,
    EvaluatorThresholds,
    StrategyMetrics,
    TradeRecord,
    CloseEntry,
    compute_metrics,
    match_trades,
    plan_actions,
)


def _dt(minutes: int) -> datetime:
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return base + timedelta(minutes=minutes)


def test_match_trades_pairs_closes_fifo() -> None:
    decisions = [
        DemoDecision(strategy_id="alpha", symbol="BTCUSDT", tf="15m", side="LONG", risk_pct=1.0, ts=_dt(0), payload={}),
        DemoDecision(strategy_id="beta", symbol="BTCUSDT", tf="15m", side="SHORT", risk_pct=0.8, ts=_dt(5), payload={}),
    ]
    closes = [
        CloseEntry(symbol="BTCUSDT", tf="15m", pnl=12.0, before=1000.0, after=1012.0, ts=_dt(10), raw={}),
        CloseEntry(symbol="BTCUSDT", tf="15m", pnl=-5.0, before=1012.0, after=1007.0, ts=_dt(20), raw={}),
    ]
    trades, summary = match_trades(decisions, closes)
    assert summary["unmatched_closes"] == 0
    assert summary["open_decisions"] == 0
    assert trades[0].strategy_id == "alpha"
    assert trades[1].strategy_id == "beta"


def test_compute_metrics_tracks_drawdown_and_sharpe() -> None:
    trades = [
        TradeRecord(
            strategy_id="alpha",
            symbol="BTCUSDT",
            tf="15m",
            pnl=15.0,
            before=1000.0,
            after=1015.0,
            entry_ts=_dt(0),
            exit_ts=_dt(10),
            hold_minutes=10,
            risk_pct=1.0,
            side="LONG",
        ),
        TradeRecord(
            strategy_id="alpha",
            symbol="BTCUSDT",
            tf="15m",
            pnl=-30.0,
            before=1015.0,
            after=985.0,
            entry_ts=_dt(20),
            exit_ts=_dt(40),
            hold_minutes=20,
            risk_pct=1.2,
            side="SHORT",
        ),
    ]
    metrics = compute_metrics(trades)
    alpha = metrics["alpha"]
    assert alpha.trades == 2
    assert alpha.wins == 1 and alpha.losses == 1
    assert alpha.win_rate == pytest.approx(50.0)
    assert alpha.avg_risk_pct == pytest.approx(1.1, rel=1e-6)
    assert alpha.max_drawdown_pct == pytest.approx((1015.0 - 985.0) / 1015.0 * 100.0, rel=1e-6)
    assert alpha.current_drawdown_pct == pytest.approx(alpha.max_drawdown_pct, rel=1e-6)
    assert alpha.total_pnl == pytest.approx(-15.0)


def test_plan_actions_assigns_risk_levels() -> None:
    metrics = {
        "good": StrategyMetrics(
            strategy_id="good",
            trades=20,
            wins=16,
            losses=4,
            win_rate=80.0,
            sharpe_ratio=0.9,
            max_drawdown_pct=2.0,
            current_drawdown_pct=1.0,
        ),
        "bad": StrategyMetrics(
            strategy_id="bad",
            trades=20,
            wins=6,
            losses=14,
            win_rate=30.0,
            sharpe_ratio=0.1,
            max_drawdown_pct=3.0,
            current_drawdown_pct=2.0,
        ),
        "dd": StrategyMetrics(
            strategy_id="dd",
            trades=25,
            wins=12,
            losses=13,
            win_rate=48.0,
            sharpe_ratio=0.3,
            max_drawdown_pct=10.0,
            current_drawdown_pct=9.0,
        ),
        "new": StrategyMetrics(
            strategy_id="new",
            trades=2,
            wins=2,
            losses=0,
            win_rate=100.0,
            sharpe_ratio=1.2,
            max_drawdown_pct=0.0,
            current_drawdown_pct=0.0,
        ),
    }
    thresholds = EvaluatorThresholds(
        min_trades=5,
        min_win_rate=40.0,
        min_sharpe=0.2,
        max_drawdown_pct=6.0,
        boost_win_rate=70.0,
        boost_sharpe=0.8,
        risk_step=0.3,
        min_risk_multiplier=0.2,
        max_risk_multiplier=1.6,
    )
    plans = plan_actions(metrics, thresholds)
    assert plans["good"].action == "boost"
    assert plans["good"].risk_multiplier == pytest.approx(1.3)
    assert plans["bad"].action == "reduce_risk"
    assert plans["bad"].risk_multiplier == pytest.approx(0.7)
    assert plans["dd"].action == "disable"
    assert plans["dd"].risk_multiplier == 0.0
    assert plans["new"].action == "insufficient_data"
    assert plans["new"].risk_multiplier >= thresholds.min_risk_multiplier
