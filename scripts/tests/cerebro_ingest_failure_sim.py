#!/usr/bin/env python3
"""
Simula una ingesta fallida para probar alertas de Slack y métricas del textfile collector.

Forzamos un fallo pidiendo una fuente inexistente (`--require-sources fake_source`), de modo que el CLI
termina con código !=0 y actualiza tanto el archivo .prom como las notificaciones configuradas.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "scripts" / "ops.py"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simula una ingesta fallida para validar alertas/metricas.")
    parser.add_argument("--output", default=str(ROOT / "tmp_logs" / "cerebro_ingestion_sim.json"))
    parser.add_argument(
        "--prometheus-file",
        help="Archivo .prom donde escribir la métrica (default usa CEREBRO_INGEST_PROM_FILE o tmp).",
        default=None,
    )
    parser.add_argument(
        "--extra-args",
        nargs=argparse.REMAINDER,
        help="Argumentos adicionales a pasar al comando `python scripts/ops.py cerebro ingest ...`",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    cmd = [
        sys.executable,
        str(OPS),
        "cerebro",
        "ingest",
        "--output",
        args.output,
        "--max-tasks",
        "1",
        "--require-sources",
        "fake_source",
    ]
    if args.prometheus_file:
        cmd.extend(["--prometheus-file", args.prometheus_file])
    if args.extra_args:
        cmd.extend(args.extra_args)
    print("[cerebro-ingest-sim] Ejecutando:\n ", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, cwd=ROOT)
    except subprocess.CalledProcessError as exc:
        print("[cerebro-ingest-sim] La ingesta falló como se esperaba (esto confirma la ruta de alertas).")
        sys.exit(0)
    raise SystemExit(
        "[cerebro-ingest-sim] La ingesta no falló; ajusta --require-sources o extra args para forzar un error."
    )


if __name__ == "__main__":
    main()
