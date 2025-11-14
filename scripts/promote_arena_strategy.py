#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.arena.promote import export_strategy  # noqa: E402


def main(
    strategy_id: str,
    dest: Path | None = None,
    *,
    min_trades: int,
    min_sharpe: float,
    max_drawdown: float,
    force: bool,
) -> None:
    package_dir = export_strategy(
        strategy_id,
        dest_dir=dest,
        min_trades=min_trades,
        min_sharpe=min_sharpe,
        max_drawdown=max_drawdown,
        force=force,
    )
    print(f"Estrategia {strategy_id} exportada en {package_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Promueve una estrategia de la arena para modo real")
    parser.add_argument("strategy_id", help="ID en registry.json (ej. scalp_42)")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directorio destino (default bot/arena/promoted)")
    parser.add_argument("--min-trades", type=int, default=50, help="Trades mínimos requeridos para promover")
    parser.add_argument("--min-sharpe", type=float, default=0.2, help="Sharpe mínimo requerido")
    parser.add_argument("--max-drawdown", type=float, default=35.0, help="Max drawdown permitido (%)")
    parser.add_argument("--force", action="store_true", help="Ignora validaciones y forza exportación")
    args = parser.parse_args()
    main(
        args.strategy_id,
        args.output_dir,
        min_trades=args.min_trades,
        min_sharpe=args.min_sharpe,
        max_drawdown=args.max_drawdown,
        force=args.force,
    )
