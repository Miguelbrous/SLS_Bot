from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
from typing import Any, Dict

import requests

from . import StrategyRegistry, StrategyContext


def _sign_payload(body: bytes, secret: str, header: str) -> Dict[str, str]:
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {header: signature}


def _fetch_balance(base_url: str) -> float:
    try:
        resp = requests.get(f"{base_url}/diag", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return float(data.get("saldo_usdt") or 0.0)
    except Exception:
        return 0.0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ejecuta una estrategia y dispara el webhook del bot")
    parser.add_argument("strategy", help=f"ID de la estrategia disponible: {', '.join(StrategyRegistry.all().keys())}")
    parser.add_argument("--mode", default=os.getenv("SLSBOT_MODE", "test"), help="Modo activo (test/real)")
    parser.add_argument("--server", default="http://127.0.0.1:8080", help="URL base del bot FastAPI")
    parser.add_argument("--leverage", type=int, default=20, help="Leverage sugerido para la estrategia")
    parser.add_argument("--dry-run", action="store_true", help="Solo muestra el payload, no envía al webhook")
    parser.add_argument("--signature-secret", default=os.getenv("WEBHOOK_SHARED_SECRET"), help="Secreto para firmar el webhook")
    parser.add_argument("--signature-header", default=os.getenv("WEBHOOK_SIGNATURE_HEADER", "X-Webhook-Signature"), help="Header a utilizar para la firma")
    parser.add_argument("--verbose", action="store_true", help="Muestra más información del proceso")
    return parser.parse_args(argv)


def run_once(
    *,
    strategy_id: str,
    mode: str,
    server: str,
    leverage: int,
    signature_secret: str | None,
    signature_header: str,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    strategy = StrategyRegistry.get(strategy_id)
    balance = _fetch_balance(server)
    context = StrategyContext(
        balance=balance or 5.0,
        mode=mode,
        symbol=strategy.symbol,
        timeframe=strategy.timeframe,
        leverage=leverage,
    )
    payload = strategy.build_signal(context)
    if payload is None:
        if verbose:
            print("[runner] Estrategia no generó señal en esta iteración", file=sys.stderr)
        return 0

    body = json.dumps(payload).encode()
    if dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if signature_secret:
        headers.update(_sign_payload(body, signature_secret, signature_header))
    try:
        resp = requests.post(f"{server}/webhook", data=body, headers=headers, timeout=10)
        if verbose:
            print(f"[runner] HTTP {resp.status_code}: {resp.text}")
        resp.raise_for_status()
    except Exception as exc:
        print(f"[runner] Error enviando señal: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    return run_once(
        strategy_id=args.strategy,
        mode=args.mode,
        server=args.server,
        leverage=args.leverage,
        signature_secret=args.signature_secret,
        signature_header=args.signature_header,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
