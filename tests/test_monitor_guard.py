from __future__ import annotations

from scripts.tools import monitor_guard as guard


def test_parse_metrics_handles_simple_payload():
    payload = """
    # HELP something
    sls_arena_state_age_seconds 120
    other_metric 3.14
    """
    data = guard.parse_metrics(payload)
    assert data["sls_arena_state_age_seconds"] == 120
    assert data["other_metric"] == 3.14


def test_evaluate_issues_detects_lag_drawdown_and_ticks():
    state = {
        "last_tick_ts": None,
        "drawdown_pct": 40.0,
        "ticks_since_win": 30,
    }
    metrics = {"sls_arena_state_age_seconds": 700.0}
    issues = guard.evaluate_issues(state, metrics, lag_threshold=600, drawdown_threshold=20.0, ticks_threshold=10)
    keys = {issue["key"] for issue in issues}
    assert {"arena_lag", "arena_drawdown", "arena_stall"} <= keys
