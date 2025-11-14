#!/usr/bin/env python3
"""
Simula un fallo del comando `python scripts/ops.py cerebro autopilot ...` para validar alertas y métricas.

Por defecto fuerza la condición de "dataset con pocas filas" estableciendo `--min-rows` a un valor ridículamente alto.
Esto hace que el comando finalice con SystemExit y debería disparar tanto Slack como las métricas `cerebro_autopilot_success 0`.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "scripts" / "ops.py"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fuerza un fallo controlado del Cerebro Autopilot.")
    parser.add_argument("--mode", default="test", help="Modo a utilizar (default: test).")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Ruta al dataset JSONL. Si no existe, se usará logs/<mode>/cerebro_experience.jsonl.",
    )
    parser.add_argument(
        "--prometheus-file",
        help="Archivo .prom donde se debe escribir la métrica (opcional, puedes confiar en CEREBRO_AUTO_PROM_FILE).",
    )
    parser.add_argument(
        "--extra-args",
        nargs=argparse.REMAINDER,
        help="Argumentos extra para delegar al CLI (por ejemplo --slack-webhook ...).",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    dataset = args.dataset or (ROOT / "logs" / args.mode / "cerebro_experience.jsonl")
    log_file = ROOT / "tmp_logs" / f"cerebro_autopilot_sim_{args.mode}.log"
    cmd = [
        sys.executable,
        str(OPS),
        "cerebro",
        "autopilot",
        "--mode",
        args.mode,
        "--dataset",
        str(dataset),
        "--min-rows",
        "999999",
        "--log-file",
        str(log_file),
        "--no-promote",
        "--dry-run",
    ]
    if args.prometheus_file:
        cmd.extend(["--prometheus-file", args.prometheus_file])
    if args.extra_args:
        cmd.extend(args.extra_args)
    print("[cerebro-autopilot-sim] Ejecutando:\n ", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, cwd=ROOT)
    except subprocess.CalledProcessError:
        print("[cerebro-autopilot-sim] El comando falló como se esperaba. Verifica Slack/prometheus para confirmar.")
        sys.exit(0)
    raise SystemExit(
        "[cerebro-autopilot-sim] El comando no falló (verifica los argumentos o reduce --min-rows para forzar el error)."
    )


if __name__ == "__main__":
    main()
