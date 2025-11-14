from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from bot.app import main as app_main


def test_bot_drawdown_metric_uses_risk_state(monkeypatch):
    monkeypatch.setattr(
        app_main,
        "_load_risk_state_payload",
        lambda: ({"start_equity": 100.0, "last_entry_equity": 80.0}, {}),
    )
    assert app_main._bot_drawdown_metric() == pytest.approx(20.0)


def test_cerebro_decisions_rate_metric(tmp_path, monkeypatch):
    log_path = tmp_path / "cerebro_decisions.jsonl"
    now = datetime.now(timezone.utc)
    payloads = [
        {"ts": (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"), "action": "LONG"},
        {"ts": (now - timedelta(minutes=16)).isoformat().replace("+00:00", "Z"), "action": "SHORT"},
        {"ts": (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"), "action": "NO_TRADE"},
    ]
    with log_path.open("w", encoding="utf-8") as fh:
        for entry in payloads:
            fh.write(json.dumps(entry) + "\n")
    monkeypatch.setattr(app_main, "CEREBRO_DECISIONS_LOG", log_path)
    rate = app_main._cerebro_decisions_rate_metric()
    # Solo una decisión válida en los últimos 15 minutos -> 1/15 decisiones por minuto
    assert rate == pytest.approx(1 / 15)
