from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import bot.cerebro.router as router_module
from bot.cerebro.router import cerebro_router


class DummyCerebro:
    def __init__(self) -> None:
        self.config = SimpleNamespace(enabled=True)
        self._status = {"ok": True}
        self._decisions = [{"ts": "2024-01-01T00:00:00Z", "symbol": "BTCUSDT", "action": "LONG"}]
        self._latest = SimpleNamespace(
            action="LONG",
            confidence=0.9,
            risk_pct=1.2,
            leverage=5,
            summary="dummy",
            reasons=["ok"],
            generated_at=0,
            metadata={},
            price=100.0,
            stop_loss=90.0,
            take_profit=110.0,
            timeframe="15m",
            symbol="BTCUSDT",
            evidences={},
        )
        self.register_calls = []

    def get_status(self) -> dict:
        return self._status

    def list_decisions(self, limit: int = 50) -> list[dict]:
        return self._decisions[:limit]

    def latest_decision(self, symbol: str, timeframe: str):
        return self._latest

    def run_cycle(self) -> None:
        pass

    def register_trade(self, **payload) -> None:
        self.register_calls.append(payload)


@pytest.fixture()
def dummy_cerebro(monkeypatch) -> DummyCerebro:
    dummy = DummyCerebro()
    monkeypatch.setattr(router_module, "get_cerebro", lambda: dummy)
    return dummy


@pytest.fixture()
def client(dummy_cerebro):
    test_app = FastAPI()
    test_app.include_router(cerebro_router)
    return TestClient(test_app)


def test_cerebro_status_endpoint(dummy_cerebro: DummyCerebro, client: TestClient):
    dummy_cerebro._status = {"memory": {"total": 1}}
    resp = client.get("/cerebro/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["memory"]["total"] == 1
    assert "time" in data


def test_cerebro_decisions_endpoint(dummy_cerebro: DummyCerebro, client: TestClient):
    resp = client.get("/cerebro/decisions?limit=1")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["count"] == 1
    assert payload["rows"][0]["symbol"] == "BTCUSDT"


def test_cerebro_decide_and_learn(dummy_cerebro: DummyCerebro, client: TestClient):
    resp = client.post("/cerebro/decide", json={"symbol": "BTCUSDT", "timeframe": "15m"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "LONG"

    learn_payload = {
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "pnl": 5.1,
        "decision": "LONG",
        "features": {"confidence": 0.9},
    }
    resp = client.post("/cerebro/learn", json=learn_payload)
    assert resp.status_code == 200
    assert dummy_cerebro.register_calls
