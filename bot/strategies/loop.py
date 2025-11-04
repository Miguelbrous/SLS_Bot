from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

from ..core.settings import get_settings
from .runner import run_once

SETTINGS = get_settings()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ejecuta continuamente una estrategia del bot.")
    parser.add_argument("--strategy", default=SETTINGS.strategy.id, help="ID de la estrategia registrada.")
    parser.add_argument("--server", default=SETTINGS.strategy.server, help="URL del bot (endpoint /webhook).")
    parser.add_argument("--mode", default=SETTINGS.slsbot_mode, help="Modo activo test/real.")
    parser.add_argument("--leverage", type=int, default=SETTINGS.strategy.leverage, help="Leverage base.")
    parser.add_argument("--interval", type=int, default=SETTINGS.strategy.interval_seconds, help="Segundos entre ejecuciones.")
    parser.add_argument("--signature-secret", default=SETTINGS.strategy.signature_secret, help="Secreto para firmar webhooks.")
    parser.add_argument("--signature-header", default=SETTINGS.strategy.signature_header, help="Header usado para la firma.")
    parser.add_argument("--verbose", action="store_true", help="Muestra logs detallados.")
    parser.add_argument("--max-errors", type=int, default=SETTINGS.strategy.max_errors, help="Errores consecutivos antes de abortar (0 = infinito).")
    return parser.parse_args(argv)


def run_loop(args: argparse.Namespace) -> int:
    errors = 0
    while True:
        code = run_once(
            strategy_id=args.strategy,
            mode=args.mode,
            server=args.server,
            leverage=args.leverage,
            signature_secret=args.signature_secret,
            signature_header=args.signature_header,
            dry_run=False,
            verbose=args.verbose,
        )
        if code != 0:
            errors += 1
            if args.max_errors and errors >= args.max_errors:
                print(f"[loop] Abortando tras {errors} errores consecutivos", file=sys.stderr)
                return code
        else:
            errors = 0
        time.sleep(max(1, args.interval))


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    return run_loop(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
