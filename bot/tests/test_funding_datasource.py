from __future__ import annotations

from bot.cerebro.datasources import funding as funding_module


def test_funding_datasource_summarizes_rates(monkeypatch):
    sample_payload = {
        "result": {
            "list": [
                {"fundingRate": "0.0006", "fundingRateTimestamp": "1700000000000"},
                {"fundingRate": "-0.0002", "fundingRateTimestamp": "1699990000000"},
            ]
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

    monkeypatch.setattr(funding_module.requests, "get", fake_get)
    cfg = funding_module.FundingFeedConfig(enabled=True, cache_ttl=999, threshold=0.00025)
    ds = funding_module.FundingDataSource(cfg)
    rows = ds.fetch(symbol="BTCUSDT")
    assert rows[0]["bias"] == "longs_pay"
    assert rows[0]["history"] == 2
    assert rows[0]["symbol"] == "BTCUSDT"


def test_funding_datasource_returns_fallback_when_disabled():
    ds = funding_module.FundingDataSource(funding_module.FundingFeedConfig(enabled=False))
    rows = ds.fetch(symbol="ETHUSDT")
    assert rows[0]["bias"] == "neutral"
    assert rows[0]["symbol"] == "ETHUSDT"
