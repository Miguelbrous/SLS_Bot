#!/usr/bin/env python3
"""
Configura el directorio del textfile collector de node_exporter y crea archivos .prom placeholders.

Úsalo para preparar el entorno de métricas locales o para validar permisos antes de apuntar los cronjobs.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

DEFAULT_DIR = Path(os.getenv("NODE_EXPORTER_TEXTFILE_DIR") or "tmp_metrics/textfile")
PROM_FILES = {
    "cerebro_ingest": "cerebro_ingest.prom",
    "cerebro_autopilot": "cerebro_autopilot.prom",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepara el directorio del textfile collector para Node Exporter.")
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_DIR,
        help="Directorio donde Node Exporter lee los .prom (default = %(default)s o NODE_EXPORTER_TEXTFILE_DIR).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Sobrescribe archivos existentes con placeholders vacíos.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    target_dir: Path = args.dir.expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"[textfile] Directorio preparado: {target_dir}")
    for key, name in PROM_FILES.items():
        path = target_dir / name
        if path.exists() and not args.force:
            print(f"[textfile] {path} ya existe; usa --force si quieres sobrescribirlo.")
            continue
        path.write_text("# placeholder\n", encoding="utf-8")
        print(f"[textfile] Placeholder creado: {path}")
    print(
        "\nExporta NODE_EXPORTER_TEXTFILE_DIR en tu entorno/cron para que los scripts usen esta ruta, por ejemplo:\n"
        f'  export NODE_EXPORTER_TEXTFILE_DIR="{target_dir}"\n'
        "y define CEREBRO_AUTO_PROM_FILE/CEREBRO_INGEST_PROM_FILE si deseas rutas distintas."
    )


if __name__ == "__main__":
    main()
