#!/usr/bin/env python3
"""
Simulador/generador de ejercicios de failover para los servicios systemd del bot.

Ejemplos:

    # Dry-run (sólo imprime el plan y genera un reporte)
    python scripts/tools/failover_sim.py

    # Ejecuta reinicios reales y guarda el log en logs/failover/
    sudo python scripts/tools/failover_sim.py --execute --services sls-api.service,sls-cerebro.service,sls-bot.service
"""

from __future__ import annotations

import argparse
import datetime as dt
import shlex
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Iterable, List

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SERVICES = ["sls-api.service", "sls-cerebro.service", "sls-bot.service"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simula/ejecuta un failover de servicios systemd del bot.")
    parser.add_argument(
        "--services",
        default=",".join(DEFAULT_SERVICES),
        help="Lista separada por comas con los servicios systemd a reciclar.",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=REPO_ROOT / "logs" / "failover",
        help="Directorio donde guardar el reporte.",
    )
    parser.add_argument(
        "--max-wait",
        type=int,
        default=45,
        help="Segundos máximos para esperar a que cada servicio vuelva a 'active'.",
    )
    parser.add_argument(
        "--journal-lines",
        type=int,
        default=50,
        help="Cantidad de líneas de journalctl a capturar tras cada reinicio.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Si se indica, reinicia los servicios. Si no, sólo imprime el plan (dry-run).",
    )
    return parser.parse_args()


def _run_command(cmd: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _systemctl_status(service: str) -> str:
    proc = _run_command(["systemctl", "status", service, "--no-pager"])
    return proc.stdout or proc.stderr


def _systemctl_restart(service: str) -> subprocess.CompletedProcess[str]:
    return _run_command(["systemctl", "restart", service])


def _systemctl_is_active(service: str) -> bool:
    proc = _run_command(["systemctl", "is-active", service])
    return proc.stdout.strip() == "active"


def _journal_tail(service: str, lines: int) -> str:
    proc = _run_command(["journalctl", "-u", service, "-n", str(lines), "--no-pager"])
    return proc.stdout or proc.stderr


def _format_header(title: str) -> str:
    border = "=" * len(title)
    return f"{title}\n{border}"


def simulate_failover(
    services: Iterable[str],
    *,
    execute: bool,
    log_dir: Path,
    max_wait: int,
    journal_lines: int,
) -> Path:
    services = [svc.strip() for svc in services if svc.strip()]
    if not services:
        raise SystemExit("No se especificaron servicios.")

    log_dir.mkdir(parents=True, exist_ok=True)
    now_utc = dt.datetime.now(dt.timezone.utc)
    timestamp = now_utc.strftime("%Y%m%d_%H%M%S")
    report_path = log_dir / f"failover_report_{timestamp}.log"

    lines: List[str] = []
    lines.append(_format_header("SLS Bot Failover Simulation"))
    lines.append(f"UTC timestamp : {now_utc.isoformat()}")
    lines.append(f"Mode          : {'EXECUTE' if execute else 'DRY-RUN'}")
    lines.append(f"Services      : {', '.join(services)}")
    lines.append(f"Max wait (s)  : {max_wait}")
    lines.append("")

    for service in services:
        lines.append(_format_header(service))
        lines.append("Estado inicial:")
        lines.append(_systemctl_status(service))
        lines.append("")

        if execute:
            lines.append(f"Reiniciando {service} ...")
            restart_proc = _systemctl_restart(service)
            if restart_proc.returncode != 0:
                lines.append(f"[ERROR] systemctl restart devolvió {restart_proc.returncode}:")
                lines.append(restart_proc.stderr.strip())
                lines.append("")
                continue
            start = time.time()
            while time.time() - start < max_wait:
                if _systemctl_is_active(service):
                    break
                time.sleep(1)
            if _systemctl_is_active(service):
                lines.append(f"[OK] {service} volvió a 'active' en {time.time() - start:.1f} s.")
            else:
                lines.append(f"[WARN] {service} no está 'active' tras {max_wait} s (verificar manualmente).")
        else:
            cmd = f"systemctl restart {service}"
            lines.append("Dry-run: se ejecutaría -> " + cmd)

        lines.append("")
        lines.append("Estado posterior:")
        lines.append(_systemctl_status(service))
        lines.append("")
        lines.append(f"journalctl -u {service} (últimas {journal_lines} líneas):")
        lines.append(_journal_tail(service, journal_lines))
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def main() -> None:
    args = parse_args()
    services = args.services.split(",")
    report_path = simulate_failover(
        services,
        execute=args.execute,
        log_dir=args.log_dir,
        max_wait=args.max_wait,
        journal_lines=args.journal_lines,
    )
    print(textwrap.dedent(
        f"""
        Reporte generado: {report_path}
        Tip: usa 'sudo make failover-sim EXECUTE=1' para automatizar la ejecución real.
        """
    ).strip())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
