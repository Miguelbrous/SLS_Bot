from __future__ import annotations

from types import SimpleNamespace

import pytest

from bot.sls_bot import app as sls_app


class DummyCerebro:
    def __init__(self, decision):
        self._decision = decision
        self.learn_calls = []

    def run_cycle(self) -> None:
        pass

    def latest_decision(self, symbol: str, timeframe: str):
        return self._decision

    def register_trade(self, **payload) -> None:
        self.learn_calls.append(payload)


def make_decision(action: str = "LONG", metadata: dict | None = None):
    return SimpleNamespace(
        action=action,
        confidence=0.8,
        risk_pct=1.5,
        leverage=4,
        stop_loss=90.0,
        take_profit=110.0,
        timeframe="15m",
        symbol="BTCUSDT",
        metadata=metadata or {"news_sentiment": 0.1},
    )


@pytest.fixture(autouse=True)
def enable_cerebro(monkeypatch):
    monkeypatch.setattr(sls_app, "CEREBRO_ENABLED", True, raising=False)


def test_maybe_apply_cerebro_blocks_no_trade(monkeypatch):
    decision = make_decision(action="NO_TRADE")
    dummy = DummyCerebro(decision)
    monkeypatch.setattr(sls_app, "get_cerebro", lambda: dummy)
    sig = sls_app.Signal(signal="LONG", symbol="BTCUSDT", tf="15m")
    state = {"last_cerebro_decision": None}

    result = sls_app._maybe_apply_cerebro(sig, 30000.0, state)

    assert result and result["blocked"]
    assert state["last_cerebro_decision"]["action"] == "NO_TRADE"


def test_maybe_apply_cerebro_applies_params(monkeypatch):
    decision = make_decision(action="LONG")
    dummy = DummyCerebro(decision)
    monkeypatch.setattr(sls_app, "get_cerebro", lambda: dummy)
    sig = sls_app.Signal(signal="LONG", symbol="BTCUSDT", tf="15m", risk_pct=0.5, leverage=2)
    state = {"last_cerebro_decision": None}

    result = sls_app._maybe_apply_cerebro(sig, 30000.0, state)

    assert result and result.get("blocked") is False
    assert sig.risk_pct == decision.risk_pct
    assert sig.leverage == decision.leverage
    assert state["last_cerebro_decision"]["action"] == "LONG"


def test_notify_cerebro_learn_pushes_features(monkeypatch):
    metadata = {
        "news_sentiment": 0.2,
        "session_guard": {"state": "news_ready", "risk_multiplier": 0.7},
        "memory_win_rate": 0.6,
        "ml_score": 0.65,
    }
    state = {
        "last_cerebro_decision": {
            "action": "LONG",
            "timeframe": "15m",
            "confidence": 0.8,
            "risk_pct": 1.5,
            "leverage": 3,
            "metadata": metadata,
        }
    }
    dummy = DummyCerebro(make_decision())
    monkeypatch.setattr(sls_app, "get_cerebro", lambda: dummy)

    sls_app._notify_cerebro_learn("BTCUSDT", "15m", 10.0, state)

    assert not state["last_cerebro_decision"]
    assert dummy.learn_calls
    features = dummy.learn_calls[0]["features"]
    assert features["news_sentiment"] == 0.2
    assert features["session_guard_state"] == "news_ready"
    assert features["ml_score"] == 0.65


def test_guardrails_block_low_confidence(monkeypatch):
    guard_cfg = {"risk": {"guardrails": {"min_confidence": 0.9}}}
    monkeypatch.setattr(sls_app, "cfg", guard_cfg, raising=False)
    sig = sls_app.Signal(signal="LONG", symbol="BTCUSDT", tf="15m", risk_score=0.4, risk_pct=1.5, leverage=5)
    state = {}

    result = sls_app._apply_guardrails(sig, 30000.0, state)

    assert result and result["blocked"]
    assert state["guardrail_hits"]


def test_guardrails_cap_symbol(monkeypatch):
    guard_cfg = {
        "risk": {
            "guardrails": {
                "per_symbol": {
                    "BTCUSDT": {"max_risk_pct": 1.0, "max_leverage": 8}
                }
            }
        }
    }
    monkeypatch.setattr(sls_app, "cfg", guard_cfg, raising=False)
    sig = sls_app.Signal(signal="LONG", symbol="BTCUSDT", tf="15m", risk_pct=2.5, leverage=15)
    state = {}

    result = sls_app._apply_guardrails(sig, 30000.0, state)

    assert not result or not result.get("blocked")
    assert sig.risk_pct == 1.0
    assert sig.leverage == 8
    assert state["guardrail_hits"]
