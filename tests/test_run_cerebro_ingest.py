from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from scripts.tools import run_cerebro_ingest as ingest


class DummyConfig(SimpleNamespace):
    symbols = ["BTCUSDT"]
    timeframes = ["1m"]
    news_feeds = {"enabled": True}
    macro_feeds = {}
    orderflow_feeds = {"enabled": True}
    funding_feeds = {"enabled": True}
    onchain_feeds = {"enabled": True}
    data_cache_ttl = 60


class DummyManager:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.scheduled = []

    def warmup(self, symbols, timeframes):
        self.warmed = (symbols, timeframes)

    def schedule(self, task):
        self.scheduled.append(task)

    def run_pending(self, max_tasks):
        return {
            "market:BTCUSDT:1m": [{"close": 10}, {"close": 11}],
            "news:global": [{"title": "headline"}],
            "funding:BTCUSDT": [{}],
        }


def test_run_builds_summary_and_writes_output(monkeypatch, tmp_path):
    monkeypatch.setattr(ingest, "load_cerebro_config", lambda: DummyConfig())
    monkeypatch.setattr(ingest, "DataIngestionManager", DummyManager)
    output = tmp_path / "ingest.json"
    parser = ingest.build_parser()
    args = parser.parse_args(
        [
            "--symbols",
            "BTCUSDT",
            "--include-news",
            "--include-funding",
            "--output",
            str(output),
        ]
    )
    summary = ingest.run(args)
    assert summary["rows_by_source"]["market"] == 2
    assert summary["rows_by_source"]["news"] == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["rows_by_source"]["funding"] == 1


def test_write_prometheus_handles_empty_summary(tmp_path):
    prom = tmp_path / "metrics.prom"
    ingest._write_prometheus_file(str(prom), {}, True)
    content = prom.read_text(encoding="utf-8")
    assert "cerebro_ingest_success 1" in content
    assert "cerebro_ingest_last_ts" in content


def test_post_slack_uses_timeout_and_proxy(monkeypatch):
    called = {}

    def fake_post(url, json=None, timeout=None, proxies=None):
        called["timeout"] = timeout
        called["proxies"] = proxies

        class DummyResponse:
            def raise_for_status(self):
                return None

        return DummyResponse()

    monkeypatch.setattr(ingest.requests, "post", fake_post)
    ingest._post_slack(
        "https://hooks.slack.test",
        "ok",
        username="cerebro-ingest",
        timeout=7.5,
        proxy="http://proxy.local:8080",
    )
    assert called["timeout"] == 7.5
    assert called["proxies"] == {"http": "http://proxy.local:8080", "https": "http://proxy.local:8080"}
