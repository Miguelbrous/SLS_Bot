from __future__ import annotations

from bot.cerebro.datasources import orderflow as orderflow_module


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_orderflow_fetch_aggregates(monkeypatch):
    payload = {
        "retCode": 0,
        "result": {
            "a": [["100.5", "2"], ["100.6", "1"]],
            "b": [["100.4", "3"], ["100.3", "1"]],
        },
    }

    def fake_get(url, params, timeout):
        return DummyResponse(payload)

    monkeypatch.setattr(orderflow_module.requests, "get", fake_get)
    cfg = orderflow_module.OrderflowConfig(enabled=True)
    ds = orderflow_module.OrderflowDataSource(cfg)
    rows = ds.fetch(symbol="BTCUSDT", limit=1)
    assert rows
    data = rows[0]
    assert data["symbol"] == "BTCUSDT"
    assert abs(data["liquidity_imbalance"]) > 0
    assert data["best_bid"] == 100.4
    assert data["best_ask"] == 100.5
