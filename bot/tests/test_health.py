import os
from pathlib import Path

from fastapi.testclient import TestClient

# Asegurar que FastAPI use el config de ejemplo y evitar llamadas externas al importar
CONFIG_SAMPLE = Path(__file__).resolve().parents[3] / "config" / "config.sample.json"
os.environ.setdefault("SLSBOT_CONFIG", str(CONFIG_SAMPLE))
os.environ.setdefault("SLS_SKIP_TIME_SYNC", "1")

from sls_bot.app import app  # noqa: E402  pylint: disable=wrong-import-position

client = TestClient(app)


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
    assert "time" in payload

