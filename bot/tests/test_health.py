import base64
import json
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODE = os.getenv("SLSBOT_MODE", "test")
LOGS_DIR = PROJECT_ROOT / "logs" / MODE
LOGS_DIR.mkdir(parents=True, exist_ok=True)
PNL_LOG_PATH = LOGS_DIR / "test_pnl.jsonl"
PNL_LOG_PATH.write_text("", encoding="utf-8")
PNL_SYMBOLS_PATH = LOGS_DIR / "test_pnl_symbols.json"
PNL_SYMBOLS_PATH.write_text("{}", encoding="utf-8")
RISK_STATE_PATH = LOGS_DIR / "risk_state.json"
RISK_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("BRIDGE_LOG", str(LOGS_DIR / "bridge.log"))
os.environ.setdefault("DECISIONS_LOG", str(LOGS_DIR / "decisions.jsonl"))
os.environ.setdefault("CONTROL_USER", "tester")
os.environ.setdefault("CONTROL_PASSWORD", "secret")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")
os.environ.setdefault("SLSBOT_CONFIG", str(PROJECT_ROOT / "config" / "config.sample.json"))
PANEL_TOKEN = "panel-token"
os.environ.setdefault("PANEL_API_TOKEN", PANEL_TOKEN)
os.environ.setdefault("PANEL_API_TOKENS", f"{PANEL_TOKEN}@2099-01-01")
os.environ.setdefault("PNL_LOG", str(PNL_LOG_PATH))
os.environ.setdefault("PNL_SYMBOLS_JSON", str(PNL_SYMBOLS_PATH))
os.environ["TRUST_PROXY_BASIC"] = "1"
os.environ["PROXY_BASIC_HEADER"] = "X-Forwarded-User"

from app.main import app  # noqa: E402  pylint: disable=wrong-import-position
import app.main as api_main  # type: ignore

client = TestClient(app)
assert api_main.TRUST_PROXY_BASIC is True


def _auth_headers(user: str = "tester", password: str = "secret") -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _panel_headers() -> dict[str, str]:
    return {"X-Panel-Token": PANEL_TOKEN}


def _write_pnl(entries: list[dict]) -> None:
    with PNL_LOG_PATH.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")
    _write_symbol_breakdown({})


def _write_symbol_breakdown(payload: dict) -> None:
    PNL_SYMBOLS_PATH.write_text(json.dumps(payload), encoding="utf-8")


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
    assert "time" in payload


@patch("app.main.service_status", return_value=(True, "mocked"))
def test_status_requires_panel_token_header(mock_status) -> None:
    response = client.get("/status")
    assert response.status_code == 401
    mock_status.assert_not_called()


@patch("app.main.service_status", return_value=(True, "mocked"))
def test_status_with_token_header(mock_status) -> None:
    response = client.get("/status", headers=_panel_headers())
    assert response.status_code == 200
    mock_status.assert_called()


@patch("app.main.service_action", return_value=(True, "mocked"))
def test_control_endpoint_requires_basic_auth(mock_action) -> None:
    response = client.post("/control/sls-bot/status")
    assert response.status_code == 401
    mock_action.assert_not_called()


@patch("app.main.service_action", return_value=(True, "mocked"))
def test_control_endpoint_accepts_valid_basic_auth(mock_action) -> None:
    response = client.post("/control/sls-bot/status", headers=_auth_headers())
    assert response.status_code == 200
    assert response.json()["ok"] is True
    mock_action.assert_called_once()


@patch("app.main.service_action", return_value=(True, "mocked"))
def test_control_endpoint_accepts_forwarded_user_header(mock_action) -> None:
    response = client.post("/control/sls-bot/status", headers={"x-forwarded-user": "nginx"})
    assert response.status_code == 200
    mock_action.assert_called_once()


def test_pnl_endpoint_aggregates_daily_entries() -> None:
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    _write_pnl([
        {"type": "close", "ts": f"{today}T10:00:00Z", "pnl": 15.5},
        {"type": "daily", "day": str(yesterday), "pnl_eur": -5.0},
    ])
    response = client.get("/pnl/diario?days=2", headers=_panel_headers())
    assert response.status_code == 200
    data = response.json()["days"]
    assert len(data) == 2
    assert any(item["day"] == str(yesterday) and item["pnl_eur"] == -5.0 for item in data)
    today_entry = next(item for item in data if item["day"] == str(today))
    assert today_entry["pnl_eur"] == 15.5
    assert today_entry["symbols"] == []
    assert today_entry["from_fills"] is False


def test_pnl_endpoint_prefers_symbol_breakdown() -> None:
    today = datetime.now(timezone.utc).date()
    _write_pnl([{"type": "close", "ts": f"{today}T09:00:00Z", "pnl": -1.0}])
    _write_symbol_breakdown({
        str(today): {
            "total": 25.0,
            "symbols": {
                "BTCUSDT": {"pnl": 20.0, "fees": -0.3, "trades": 1},
                "ETHUSDT": {"pnl": 5.0, "fees": -0.1, "trades": 2},
            },
        }
    })
    response = client.get("/pnl/diario?days=1", headers=_panel_headers())
    assert response.status_code == 200
    payload = response.json()["days"][0]
    assert payload["from_fills"] is True
    assert payload["pnl_eur"] == 25.0
    symbols = {entry["symbol"]: entry for entry in payload["symbols"]}
    assert symbols["BTCUSDT"]["pnl_eur"] == 20.0
    assert symbols["ETHUSDT"]["trades"] == 2


@patch("app.main.service_status", return_value=(True, "mocked"))
def test_status_exposes_risk_state_details(mock_status) -> None:
    RISK_STATE_PATH.write_text(json.dumps({
        "consecutive_losses": 3,
        "cooldown_until_ts": int(datetime.now(timezone.utc).timestamp()) + 600,
        "active_cooldown_reason": "loss_streak",
        "recent_results": [{"pnl": -2.0}, {"pnl": 1.0}],
        "cooldown_history": [{"ts": datetime.now(timezone.utc).isoformat(), "reason": "loss_streak", "minutes": 30}],
    }), encoding="utf-8")
    response = client.get("/status", headers=_panel_headers())
    assert response.status_code == 200
    mock_status.assert_called()
    details = response.json()["bot"]["risk_state_details"]
    assert details["active_cooldown_reason"] == "loss_streak"
    assert details["consecutive_losses"] == 3
    assert len(details["recent_results"]) == 2


def test_autopilot_summary_endpoint(tmp_path) -> None:
    summary_file = tmp_path / "autopilot.json"
    summary_file.write_text(
        json.dumps(
            {
                "dataset": {"summary": {"total": 3, "win_rate": 0.5, "dominant_symbol_share": 0.4}, "violations": []},
                "arena": {"accepted": [{"name": "alpha", "score": 1.2, "stats": {"sharpe": 1.5, "max_drawdown": 3, "profit_factor": 2.0, "win_rate": 0.6, "trades": 120, "feature_drift": 0.1}}], "rejected": []},
            }
        ),
        encoding="utf-8",
    )
    prev = api_main.AUTOPILOT_SUMMARY_JSON
    api_main.AUTOPILOT_SUMMARY_JSON = summary_file
    try:
        response = client.get("/autopilot/summary", headers=_panel_headers())
        assert response.status_code == 200
        payload = response.json()
        assert payload["arena"]["accepted"][0]["name"] == "alpha"
    finally:
        api_main.AUTOPILOT_SUMMARY_JSON = prev

