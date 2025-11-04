#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.arena.promote import export_strategy  # noqa: E402


def main(strategy_id: str, dest: Path | None = None) -> None:
    package_dir = export_strategy(strategy_id, dest_dir=dest)
    print(f"Estrategia {strategy_id} exportada en {package_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Promueve una estrategia de la arena para modo real")
    parser.add_argument("strategy_id", help="ID en registry.json (ej. scalp_42)")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directorio destino (default bot/arena/promoted)")
    args = parser.parse_args()
    main(args.strategy_id, args.output_dir)
