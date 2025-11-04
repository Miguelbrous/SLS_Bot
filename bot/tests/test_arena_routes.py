from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def arena_module(tmp_path, monkeypatch):
    ranking_data = [
        {"name": "alpha", "score": 1.1, "category": "scalp", "balance": 120.0, "goal": 150.0},
        {"name": "beta", "score": 0.9, "category": "swing", "balance": 90.0, "goal": 140.0},
    ]
    ranking_file = tmp_path / "ranking.json"
    ranking_file.write_text(json.dumps(ranking_data), encoding="utf-8")

    state_payload = {
        "current_goal": 150.0,
        "wins": 2,
        "last_tick_ts": "2025-01-01T00:00:00Z",
        "ticks_since_win": 0,
        "drawdown_pct": 12.5,
    }
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(state_payload), encoding="utf-8")

    monkeypatch.setenv("ARENA_RANKING_PATH", str(ranking_file))
    monkeypatch.setenv("ARENA_STATE_PATH", str(state_file))
    monkeypatch.setenv("ARENA_DB_PATH", str(tmp_path / "arena.db"))
    monkeypatch.setenv("PANEL_API_TOKENS", "token123")

    module = importlib.reload(importlib.import_module("bot.app.main"))
    return module


@pytest.fixture()
def arena_client(arena_module):
    return TestClient(arena_module.app)


HEADERS = {"X-Panel-Token": "token123"}


def test_arena_ranking_endpoint(arena_client: TestClient):
    resp = arena_client.get("/arena/ranking", headers=HEADERS)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["count"] == 2
    assert payload["ranking"][0]["name"] == "alpha"


def test_arena_state_endpoint(arena_client: TestClient):
    resp = arena_client.get("/arena/state", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["wins"] == 2


def test_arena_ledger_endpoint(monkeypatch, arena_module):
    captured = {}

    class DummyStorage:
        def __init__(self, path: Path) -> None:
            captured["path"] = path

        def ledger_for(self, strategy_id: str, limit: int):
            captured["strategy_id"] = strategy_id
            captured["limit"] = limit
            return [{"pnl": 5.0}]

    monkeypatch.setattr("bot.arena.storage.ArenaStorage", DummyStorage)
    client = TestClient(arena_module.app)
    resp = client.get("/arena/ledger?strategy_id=strat_a&limit=25", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["entries"][0]["pnl"] == 5.0
    assert captured["strategy_id"] == "strat_a"
    assert captured["limit"] == 25


def test_arena_tick_invokes_service(monkeypatch, arena_module):
    called = {"tick": 0}

    class DummyService:
        def tick(self) -> None:
            called["tick"] += 1

    monkeypatch.setattr("bot.arena.service.ArenaService", lambda: DummyService())
    client = TestClient(arena_module.app)
    resp = client.post("/arena/tick", headers=HEADERS)
    assert resp.status_code == 200
    assert called["tick"] == 1


def test_arena_promote_uses_exporter(monkeypatch, arena_module):
    exported = {}

    def fake_export(strategy_id: str, **kwargs) -> Path:
        exported["id"] = strategy_id
        exported["kwargs"] = kwargs
        return Path("/tmp/pkg")

    monkeypatch.setattr("bot.arena.promote.export_strategy", fake_export)
    client = TestClient(arena_module.app)
    resp = client.post(
        "/arena/promote?strategy_id=strat_x&min_trades=60&min_sharpe=0.4&max_drawdown=25&force=true",
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert exported["id"] == "strat_x"
    assert exported["kwargs"]["min_trades"] == 60
    assert exported["kwargs"]["force"] is True


def test_arena_notes_endpoints(monkeypatch, arena_module):
    class DummyStorage:
        def __init__(self, *args, **kwargs):
            pass

        def notes_for(self, strategy_id: str, limit: int):
            return [{"strategy_id": strategy_id, "note": "hola", "author": "ops", "ts": "2025"}]

        def add_note(self, strategy_id: str, note: str, author: str | None = None):
            return {"strategy_id": strategy_id, "note": note, "author": author, "ts": "2025"}

    monkeypatch.setattr("bot.arena.storage.ArenaStorage", DummyStorage)
    client = TestClient(arena_module.app)
    resp = client.get("/arena/notes?strategy_id=strat_x", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["notes"][0]["note"] == "hola"

    resp = client.post(
        "/arena/notes",
        json={"strategy_id": "strat_x", "note": "listo", "author": "panel"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["note"] == "listo"
