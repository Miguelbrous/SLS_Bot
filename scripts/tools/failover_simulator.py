#!/usr/bin/env python3
"""
Simulador/controlador de failover para SLS_Bot.

Reinicia los servicios críticos en orden, ejecuta healthchecks y genera un reporte
en tmp_logs/failover_report_<timestamp>.log. Por defecto dry-run (no ejecuta systemctl).
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
from pathlib import Path
from typing import Iterable, List

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "tmp_logs"
SERVICES_ORDER = ["sls-bot.service", "sls-cerebro.service", "sls-api.service"]


def log(message: str, *, stream=None) -> None:
    stream = stream or print
    stream(message)


def run_command(cmd: List[str], execute: bool, report_lines: List[str]) -> None:
    report_lines.append("$ " + " ".join(cmd))
    if execute:
        subprocess.run(cmd, check=True)
    else:
        report_lines.append("(dry-run) comando no ejecutado")


def systemctl(action: str, services: Iterable[str], execute: bool, report_lines: List[str]) -> None:
    for service in services:
        run_command(["systemctl", action, service], execute, report_lines)


def healthcheck(api_base: str, panel_token: str | None, execute: bool, report_lines: List[str]) -> None:
    cmd = ["python", str(ROOT / "scripts" / "tools" / "healthcheck.py"), "--base-url", api_base]
    if panel_token:
        cmd.extend(["--panel-token", panel_token])
    run_command(cmd, execute, report_lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Simula un failover/restart ordenado de SLS_Bot.")
    parser.add_argument("--execute", action="store_true", help="Ejecuta systemctl/healthcheck (requiere sudo).")
    parser.add_argument("--api-base", default="http://127.0.0.1:8880", help="Base URL para healthcheck (default http://127.0.0.1:8880).")
    parser.add_argument("--panel-token", help="Token del panel para endpoints protegidos en healthcheck.")
    parser.add_argument("--services", nargs="+", default=SERVICES_ORDER, help="Servicios systemd a operar (orden de reinicio).")
    parser.add_argument("--output", help="Ruta del reporte (default tmp_logs/failover_report_<timestamp>.log)")
    parser.add_argument("--restart", action="store_true", help="Reinicia servicios (stop/start). Si no se especifica, solo status + health.")
    args = parser.parse_args()

    report_lines: List[str] = []
    now = dt.datetime.now(dt.timezone.utc)
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    output = Path(args.output) if args.output else LOG_DIR / f"failover_report_{timestamp}.log"
    output.parent.mkdir(parents=True, exist_ok=True)

    report_lines.append(f"# Failover report :: {now.isoformat()}")
    report_lines.append(f"# execute={args.execute} restart={args.restart}")
    report_lines.append("")

    # Registrar status pre
    report_lines.append("## Estado inicial")
    run_command(["systemctl", "status", "--no-pager", "--lines", "3", *args.services], args.execute, report_lines)
    report_lines.append("")

    if args.restart:
        report_lines.append("## Restart ordenado")
        systemctl("stop", reversed(args.services), args.execute, report_lines)
        systemctl("start", args.services, args.execute, report_lines)
        report_lines.append("")

    report_lines.append("## Healthcheck")
    healthcheck(args.api_base, args.panel_token, args.execute, report_lines)
    report_lines.append("")

    report_lines.append("## Estado final")
    run_command(["systemctl", "status", "--no-pager", "--lines", "3", *args.services], args.execute, report_lines)

    output.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(f"[failover] Reporte escrito en {output}. Ejecuta con --execute para aplicar cambios reales.")


if __name__ == "__main__":
    main()
