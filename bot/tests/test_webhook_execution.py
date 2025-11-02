import importlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def bot_module_factory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    def loader() -> object:
        monkeypatch.setenv(
            "SLSBOT_CONFIG",
            str(Path(__file__).resolve().parents[2] / "config" / "config.sample.json"),
        )
        monkeypatch.setenv("SLSBOT_MODE", "test")
        monkeypatch.setenv("SLS_SKIP_TIME_SYNC", "1")
        monkeypatch.setenv("SLS_BOT_SKIP_THREADS", "1")

        module = importlib.import_module("sls_bot.app")
        module = importlib.reload(module)

        logs_dir = tmp_path / "logs"
        excel_dir = tmp_path / "excel"
        logs_dir.mkdir(parents=True, exist_ok=True)
        excel_dir.mkdir(parents=True, exist_ok=True)

        module.LOGS_DIR = logs_dir
        module.EXCEL_DIR = excel_dir
        module.DECISIONS_LOG = logs_dir / "decisions.jsonl"
        module.BRIDGE_LOG = logs_dir / "bridge.log"
        module._STATE_FILE = logs_dir / "risk_state.json"
        module.PNL_LOG = logs_dir / "pnl.jsonl"
        module.PNL_SYMBOLS_JSON = logs_dir / "pnl_daily_symbols.json"
        module.DECISIONS_LOG.write_text("", encoding="utf-8")

        monkeypatch.setattr(module, "append_operacion", lambda *a, **k: None)
        monkeypatch.setattr(module, "append_evento", lambda *a, **k: None)
        monkeypatch.setattr(module, "_append_decision_log", lambda *a, **k: None)
        monkeypatch.setattr(module, "_append_bridge_log", lambda *a, **k: None)
        monkeypatch.setattr(module, "_append_pnl_entry", lambda *a, **k: None)
        monkeypatch.setattr(module, "_load_symbol_pnl_cache", lambda: {})
        monkeypatch.setattr(module, "_save_symbol_pnl_cache", lambda payload: None)
        monkeypatch.setattr(module, "_autopilot_tp1_and_be", lambda *a, **k: None)
        monkeypatch.setattr(
            module,
            "_create_order_signed",
            lambda payload: {"retCode": 0, "result": {"orderId": "TEST123", "orderType": payload.get("orderType", "Market")}},
        )

        class DummyResponse:
            def __init__(self, data: dict):
                self._data = data

            def json(self) -> dict:
                return self._data

        monkeypatch.setattr(
            module.requests,
            "post",
            lambda *a, **k: DummyResponse({"retCode": 0, "result": {"orderId": "TEST123", "orderType": "Market"}}),
        )

        class FakeSession:
            def __init__(self):
                self.orders = []

            def place_order(self, **kwargs):
                self.orders.append(kwargs)
                return {
                    "retCode": 0,
                    "result": {"orderId": "TEST123", "orderType": kwargs.get("orderType", "Market")},
                }

            def get_positions(self, **kwargs):
                return {"retCode": 0, "result": {"list": []}}

            def set_trading_stop(self, **kwargs):
                return {"retCode": 0}

            def get_instruments_info(self, **kwargs):
                return {
                    "retCode": 0,
                    "result": {
                        "list": [
                            {
                                "priceFilter": {"tickSize": "0.5"},
                                "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001", "maxOrderQty": "100"},
                            }
                        ]
                    },
                }

            def get_tickers(self, **kwargs):
                return {"retCode": 0, "result": {"list": [{"markPrice": "50000"}]}}

        class FakeBybit:
            def __init__(self):
                self.session = FakeSession()

            def get_balance(self):
                return 1000.0

            def get_mark_price(self, symbol: str):
                return 50000.0

            def set_leverage(self, symbol: str, buy: int, sell: int, category: str = "linear"):
                return {"retCode": 0}

        module.bb = FakeBybit()

        return module

    return loader


def _default_payload():
    return {
        "signal": "SLS_LONG_ENTRY",
        "symbol": "BTCUSDT",
        "tf": "15m",
        "price": 50010.0,
        "risk_pct": 0.5,
        "leverage": 10,
        "risk_score": 1.0,
        "post_only": False,
    }


def test_webhook_entry_executes_without_block(bot_module_factory):
    module = bot_module_factory()
    client = TestClient(module.app)
    response = client.post("/webhook", json=_default_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["order_type"] in {"Limit", "Market"}


def test_webhook_signature_guard(bot_module_factory, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WEBHOOK_SHARED_SECRET", "s3cret")
    module = bot_module_factory()
    client = TestClient(module.app)
    payload = _default_payload()
    body = json.dumps(payload).encode()
    import hmac
    import hashlib

    signature = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    headers = {"X-Webhook-Signature": signature, "Content-Type": "application/json"}

    response = client.post("/webhook", data=body, headers=headers)
    assert response.status_code == 200
    response_bad = client.post(
        "/webhook", data=body, headers={"X-Webhook-Signature": "deadbeef", "Content-Type": "application/json"}
    )
    assert response_bad.status_code == 401


def test_stop_limit_payload(bot_module_factory, monkeypatch: pytest.MonkeyPatch):
    module = bot_module_factory()
    captured: dict = {}

    class DummyResponse:
        def __init__(self, payload: dict):
            self._payload = payload

        def json(self) -> dict:
            captured["payload"] = self._payload
            return {"retCode": 0, "result": {"orderId": "STOP123", "orderType": self._payload.get("orderType")}}

    def fake_post(url, headers=None, data=None, timeout=None):
        payload = json.loads(data)
        return DummyResponse(payload)

    monkeypatch.setattr(module.requests, "post", fake_post)
    client = TestClient(module.app)
    payload = _default_payload()
    payload.update({
        "order_type": "STOP_LIMIT",
        "trigger_price": payload["price"] + 20,
        "price": payload["price"] + 10,
        "post_only": False,
    })
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    placed = captured["payload"]
    assert placed["orderType"] == "Limit"
    assert placed["orderFilter"] == "StopOrder"
    assert float(placed["triggerPrice"]) > payload["price"]


def test_low_capital_guard_adjusts_leverage(bot_module_factory, monkeypatch: pytest.MonkeyPatch):
    module = bot_module_factory()
    captured: dict = {"leverage": None}

    def tiny_balance() -> float:
        return 5.0

    def record_leverage(symbol: str, buy: int, sell: int, category: str = "linear") -> dict:
        captured["leverage"] = buy
        return {"retCode": 0}

    module.bb.get_balance = tiny_balance  # type: ignore[attr-defined]
    module.bb.set_leverage = record_leverage  # type: ignore[attr-defined]

    client = TestClient(module.app)
    payload = _default_payload()
    payload.update({"risk_pct": 1.0, "leverage": 10})
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    assert captured["leverage"] is not None
    assert captured["leverage"] >= 10
