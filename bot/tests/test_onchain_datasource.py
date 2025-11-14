from __future__ import annotations

from bot.cerebro.datasources import onchain as onchain_module


def test_onchain_fetch_builds_summary(monkeypatch):
    sample_payload = {
        "data": {
            "data": {
                "mempool_transactions": 5000,
                "transactions_24h": 100000,
                "hash_rate_24h": 124.5,
                "fees_24h_usd": 200000,
                "transactions_last_24_hours": 90000,
            }
        }
    }

    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_get(*args, **kwargs):
        return DummyResponse(sample_payload)

    monkeypatch.setattr(onchain_module.requests, "get", fake_get)
    cfg = onchain_module.OnchainFeedConfig(enabled=True)
    ds = onchain_module.OnchainDataSource(cfg)
    rows = ds.fetch(symbol="BTCUSDT")
    summary = rows[0]
    assert summary["symbol"] == "BTCUSDT"
    assert summary["mempool_ratio"] == 0.05
    assert summary["whale_bias"] in {"neutral", "sell_pressure", "buy_pressure"}


def test_onchain_disabled_returns_fallback():
    ds = onchain_module.OnchainDataSource(onchain_module.OnchainFeedConfig(enabled=False))
    row = ds.fetch(symbol="ETHUSDT")[0]
    assert row["whale_bias"] == "neutral"
