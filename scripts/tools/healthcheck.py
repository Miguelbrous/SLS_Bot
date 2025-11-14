#!/usr/bin/env python3
"""
Healthcheck sencillo para los endpoints principales del backend.

Ejemplo:
    python scripts/tools/healthcheck.py --base-url http://127.0.0.1:8880 \\
        --panel-token mi_token --control-user admin --control-password secret
"""

from __future__ import annotations

import argparse
import json
from typing import Dict, List

import requests


def _maybe_trim(data: str, limit: int = 400) -> str:
    return data if len(data) <= limit else f"{data[:limit]}...(+{len(data) - limit} chars)"


def _call_endpoint(
    base_url: str,
    method: str,
    path: str,
    headers: Dict[str, str],
    timeout: float,
    required: bool,
) -> Dict[str, object]:
    url = f"{base_url}{path}"
    summary: Dict[str, object] = {"method": method, "path": path, "required": required}
    try:
        resp = requests.request(method, url, headers=headers, timeout=timeout)
        summary["status_code"] = resp.status_code
        summary["ok"] = resp.ok
        if "application/json" in resp.headers.get("Content-Type", ""):
            try:
                payload = resp.json()
            except ValueError:
                payload = _maybe_trim(resp.text)
            summary["detail"] = payload
        else:
            summary["detail"] = _maybe_trim(resp.text)
    except Exception as exc:  # pragma: no cover - dependencias externas
        summary["ok"] = False
        summary["error"] = str(exc)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida endpoints críticos de la API del bot.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8880", help="URL base de la API (por defecto 127.0.0.1:8880).")
    parser.add_argument("--panel-token", default=None, help="Token X-Panel-Token para endpoints del panel.")
    parser.add_argument("--control-user", default=None, help="Usuario Basic Auth para /control/*.")
    parser.add_argument("--control-password", default=None, help="Password Basic Auth para /control/*.")
    parser.add_argument("--timeout", type=float, default=5.0, help="Timeout en segundos por request.")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    headers_panel: Dict[str, str] = {}
    if args.panel_token:
        headers_panel["X-Panel-Token"] = args.panel_token
    headers_control: Dict[str, str] = {}
    if args.control_user and args.control_password:
        from base64 import b64encode

        token = b64encode(f"{args.control_user}:{args.control_password}".encode()).decode()
        headers_control["Authorization"] = f"Basic {token}"

    checks: List[Dict[str, object]] = []
    checks.append(_call_endpoint(base, "GET", "/health", {}, args.timeout, required=True))

    if headers_panel:
        checks.append(_call_endpoint(base, "GET", "/status", headers_panel, args.timeout, required=True))
        checks.append(_call_endpoint(base, "GET", "/pnl/diario?days=3", headers_panel, args.timeout, required=False))
        checks.append(_call_endpoint(base, "GET", "/cerebro/status", headers_panel, args.timeout, required=False))
    else:
        checks.append({"path": "/status", "method": "GET", "required": False, "ok": False, "skipped": True, "detail": "sin panel-token"})

    if headers_control:
        checks.append(_call_endpoint(base, "POST", "/control/sls-bot/status", headers_control, args.timeout, required=False))
    else:
        checks.append({"path": "/control/sls-bot/status", "method": "POST", "required": False, "ok": False, "skipped": True, "detail": "sin credenciales control"})

    overall_ok = all(entry.get("ok", False) or not entry.get("required") for entry in checks)
    result = {"base_url": base, "ok": overall_ok, "checks": checks}
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not overall_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
