"""
Smoke test muy liviano para validar un despliegue real.
Requiere que la API esté corriendo y que existan tokens/control user.
"""
from __future__ import annotations

import base64
import os
import sys
from typing import List

import requests


API_BASE = os.environ.get("SLS_API_BASE", "http://127.0.0.1:8880").rstrip("/")
PANEL_TOKEN = os.environ.get("SLS_PANEL_TOKEN")
CONTROL_USER = os.environ.get("SLS_CONTROL_USER")
CONTROL_PASSWORD = os.environ.get("SLS_CONTROL_PASSWORD")


def _panel_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    if PANEL_TOKEN:
        headers["X-Panel-Token"] = PANEL_TOKEN
    return headers


def _control_headers() -> dict[str, str]:
    if not CONTROL_USER or not CONTROL_PASSWORD:
        return {}
    token = base64.b64encode(f"{CONTROL_USER}:{CONTROL_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def main() -> int:
    failures: List[str] = []
    try:
        resp = requests.get(f"{API_BASE}/health", timeout=5)
        resp.raise_for_status()
    except Exception as exc:  # pragma: no cover - ejecución externa
        failures.append(f"/health: {exc}")

    try:
        resp = requests.get(f"{API_BASE}/pnl/diario?days=3", headers=_panel_headers(), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if "days" not in data:
            failures.append("/pnl/diario: respuesta sin 'days'")
    except Exception as exc:  # pragma: no cover
        failures.append(f"/pnl/diario: {exc}")

    ctrl_headers = _control_headers()
    if ctrl_headers:
        try:
            resp = requests.post(f"{API_BASE}/control/sls-bot/status", headers=ctrl_headers, timeout=10)
            resp.raise_for_status()
        except Exception as exc:  # pragma: no cover
            failures.append(f"/control/sls-bot/status: {exc}")
    else:
        print(">> Omitiendo /control/*: faltan SLS_CONTROL_USER/PASSWORD", file=sys.stderr)

    if failures:
        print("Smoke test falló:")
        for fail in failures:
            print(f"  - {fail}")
        return 1
    print("Smoke test OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
