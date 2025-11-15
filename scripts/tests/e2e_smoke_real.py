#!/usr/bin/env python3
"""
Smoke test para producción real.
Verifica /health, /risk y envía una señal SLS_* con dry_run=True para validar el webhook sin colocar órdenes reales.
"""
from __future__ import annotations

import os
import sys
from typing import Dict

import requests


API_BASE = os.environ.get("SLS_API_BASE", "http://127.0.0.1:8880").rstrip("/")
PANEL_TOKEN = os.environ.get("SLS_PANEL_TOKEN")
SYMBOL = os.environ.get("SMOKE_REAL_SYMBOL", "BTCUSDT").upper()
SESSION = os.environ.get("SMOKE_REAL_SESSION", "smoke-real")
TIMEFRAME = os.environ.get("SMOKE_REAL_TF", "5m")


def _panel_headers() -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if PANEL_TOKEN:
        headers["X-Panel-Token"] = PANEL_TOKEN
    return headers


def _assert(condition: bool, message: str) -> None:
    if not condition:
        print(f"[smoke-real] {message}", file=sys.stderr)
        raise SystemExit(1)


def main() -> int:
    headers = _panel_headers()
    try:
        resp = requests.get(f"{API_BASE}/health", timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        print(f"[smoke-real] /health falló: {exc}", file=sys.stderr)
        return 1

    try:
        resp = requests.get(f"{API_BASE}/risk", headers=headers, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        print(f"[smoke-real] /risk falló: {exc}", file=sys.stderr)
        return 1

    payload = {
        "signal": "SLS_LONG_ENTRY",
        "symbol": SYMBOL,
        "tf": TIMEFRAME,
        "risk_pct": 0.25,
        "leverage": 5,
        "risk_score": 1.0,
        "session": SESSION,
        "strategy_id": "smoke_real",
        "order_type": "MARKET",
        "post_only": False,
        "dry_run": True,
    }
    try:
        resp = requests.post(f"{API_BASE}/webhook", json=payload, headers=headers, timeout=20)
        resp.raise_for_status()
    except Exception as exc:
        print(f"[smoke-real] /webhook falló: {exc}", file=sys.stderr)
        return 1
    body = resp.json()
    _assert(body.get("status") == "dry_run", f"Respuesta inesperada en /webhook: {body}")
    print("[smoke-real] Señal dry_run aceptada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
