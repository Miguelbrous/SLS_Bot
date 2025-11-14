from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from bot.cerebro.datasources import macro as macro_module


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_http_cache(monkeypatch):
    calls = {"count": 0}

    def fake_get(url, timeout):
        calls["count"] += 1
        return DummyResponse([{"symbol": "BTCUSDT", "open_interest_change_pct": 1.0}])

    monkeypatch.setattr(macro_module.requests, "get", fake_get)
    cfg = macro_module.MacroFeedConfig(cache_ttl=60.0, retry_attempts=1)
    ds = macro_module.MacroDataSource(cfg)
    first = ds._http_fetch("http://example.com/oi")
    second = ds._http_fetch("http://example.com/oi")
    assert calls["count"] == 1
    assert first == second


def test_load_cached_file(tmp_path):
    cache = tmp_path / "macro_cache.json"
    payload = [{"symbol": "ETHUSDT", "open_interest_change_pct": 0.5}]
    cache.write_text(json.dumps(payload), encoding="utf-8")
    cfg = macro_module.MacroFeedConfig(cache_dir=str(tmp_path))
    ds = macro_module.MacroDataSource(cfg)
    rows = ds._load_cached("macro_cache.json")
    assert rows == payload
