#!/usr/bin/env python3
"""Smoke-check para el stack de observabilidad local (Prometheus/Grafana/Alertmanager)."""
from __future__ import annotations

import json
import os
import sys
from typing import Iterable

import requests


def _get(url: str, timeout: float = 5.0) -> requests.Response:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp


def check_prometheus(base_url: str) -> None:
    print(f"[observability] Prometheus -> {base_url}")
    _get(f"{base_url}/-/ready")
    rules = _get(f"{base_url}/api/v1/rules").json()
    alerts = {rule["name"] for group in rules.get("data", {}).get("groups", []) for rule in group.get("rules", [])}
    required = {"ArenaLagHigh", "ArenaDrawdownHigh", "BotDrawdownCritical", "CerebroSilent"}
    missing = required - alerts
    if missing:
        raise SystemExit(f"Faltan reglas en Prometheus: {', '.join(sorted(missing))}")
    # Query simple para asegurar métricas disponibles (aunque sean NaN)
    for metric in ("sls_bot_drawdown_pct", "sls_cerebro_decisions_per_min"):
        resp = _get(f"{base_url}/api/v1/query?query={metric}").json()
        if resp.get("status") != "success":
            raise SystemExit(f"Prometheus no pudo evaluar {metric}: {json.dumps(resp)}")


def check_grafana(base_url: str, user: str | None = None, password: str | None = None) -> None:
    print(f"[observability] Grafana -> {base_url}")
    auth = None
    if user and password:
        auth = (user, password)
    resp = requests.get(f"{base_url}/api/health", auth=auth, timeout=5.0)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("database") != "ok":
        raise SystemExit(f"Grafana no está sano: {payload}")


def check_alertmanager(base_url: str) -> None:
    print(f"[observability] Alertmanager -> {base_url}")
    _get(f"{base_url}/-/ready")
    status = _get(f"{base_url}/api/v2/status").json()
    if status.get("status") not in (None, "success") and not status.get("cluster"):
        raise SystemExit(f"Alertmanager responde estado inesperado: {status}")


def main() -> None:
    prom = os.environ.get("PROM_BASE", "http://127.0.0.1:9090")
    grafana = os.environ.get("GRAFANA_BASE")
    grafana_user = os.environ.get("GRAFANA_USER")
    grafana_password = os.environ.get("GRAFANA_PASSWORD")
    alertmanager = os.environ.get("ALERTMANAGER_BASE")

    check_prometheus(prom)
    if grafana:
        check_grafana(grafana, grafana_user, grafana_password)
    if alertmanager:
        check_alertmanager(alertmanager)
    print("[observability] Stack OK")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as exc:  # pragma: no cover - network failures
        print(f"[observability] HTTP error: {exc}", file=sys.stderr)
        sys.exit(1)
