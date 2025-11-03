from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Optional

from .runner import run_once


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ejecuta continuamente una estrategia del bot.")
    parser.add_argument("--strategy", default=os.getenv("STRATEGY_ID", "micro_scalp_v1"), help="ID de la estrategia registrada.")
    parser.add_argument("--server", default=os.getenv("STRATEGY_SERVER", "http://127.0.0.1:8080"), help="URL del bot (endpoint /webhook).")
    parser.add_argument("--mode", default=os.getenv("SLSBOT_MODE", "test"), help="Modo activo test/real.")
    parser.add_argument("--leverage", type=int, default=int(os.getenv("STRATEGY_LEVERAGE", "20")), help="Leverage base.")
    parser.add_argument("--interval", type=int, default=int(os.getenv("STRATEGY_INTERVAL", "120")), help="Segundos entre ejecuciones.")
    parser.add_argument("--signature-secret", default=os.getenv("WEBHOOK_SHARED_SECRET"), help="Secreto para firmar webhooks.")
    parser.add_argument("--signature-header", default=os.getenv("WEBHOOK_SIGNATURE_HEADER", "X-Webhook-Signature"), help="Header usado para la firma.")
    parser.add_argument("--verbose", action="store_true", help="Muestra logs detallados.")
    parser.add_argument("--max-errors", type=int, default=int(os.getenv("STRATEGY_MAX_ERRORS", "5")), help="Errores consecutivos antes de abortar (0 = infinito).")
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
