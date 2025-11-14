#!/usr/bin/env python3
"""
Extrae métricas de negocio (PnL, drawdown, slippage) desde la API y escribe un
archivo compatible con el textfile collector de Prometheus.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

import requests


def fetch_json(url: str, headers: Dict[str, str], timeout: float) -> Dict[str, object]:
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError(f"Respuesta inesperada en {url}")
    return data


def build_metrics(pnl_payload: Dict[str, object], arena_payload: Dict[str, object]) -> List[str]:
    lines: List[str] = []

    today = pnl_payload.get("today") if isinstance(pnl_payload, dict) else {}
    if isinstance(today, dict):
        pnl_value = today.get("pnl")
        drawdown = today.get("drawdown_pct") or today.get("max_drawdown_pct")
        slippage = today.get("slippage_bps")
        if isinstance(pnl_value, (int, float)):
            lines.append(f"sls_bot_daily_pnl {pnl_value}")
        if isinstance(drawdown, (int, float)):
            lines.append(f"sls_bot_drawdown_pct {drawdown}")
        if isinstance(slippage, (int, float)):
            lines.append(f"sls_bot_slippage_bps {slippage}")

    totals = pnl_payload.get("totals") if isinstance(pnl_payload, dict) else {}
    if isinstance(totals, dict):
        cumulative = totals.get("pnl")
        if isinstance(cumulative, (int, float)):
            lines.append(f"sls_bot_cumulative_pnl {cumulative}")

    if isinstance(arena_payload, dict):
        lag = arena_payload.get("ticks_since_win")
        sharpe = arena_payload.get("avg_sharpe")
        if isinstance(lag, (int, float)):
            lines.append(f"sls_arena_ticks_since_win {lag}")
        if isinstance(sharpe, (int, float)):
            lines.append(f"sls_arena_avg_sharpe {sharpe}")

    return lines


def write_prom_file(path: Path, lines: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(lines) + "\n"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera métricas de negocio para Prometheus textfile collector.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8880", help="Base URL de la API (default: http://127.0.0.1:8880).")
    parser.add_argument("--panel-token", help="Token del panel para endpoints protegidos.")
    parser.add_argument("--output", default="tmp_metrics/business.prom", help="Archivo destino .prom")
    parser.add_argument("--timeout", type=float, default=5.0, help="Timeout por request (s).")
    parser.add_argument("--pnl-file", help="Ruta local a un JSON de pnl (modo offline/test).")
    parser.add_argument("--arena-file", help="Ruta local a un JSON de arena (modo offline/test).")
    args = parser.parse_args()

    headers = {}
    if args.panel_token:
        headers["X-Panel-Token"] = args.panel_token

    api_base = args.api_base.rstrip("/")

    if args.pnl_file:
        pnl_payload = json.loads(Path(args.pnl_file).read_text(encoding="utf-8"))
    else:
        try:
            pnl_payload = fetch_json(f"{api_base}/pnl/diario", headers, args.timeout)
        except Exception as exc:
            print(f"[metrics] Error al consultar /pnl/diario: {exc}", file=sys.stderr)
            pnl_payload = {}

    if args.arena_file:
        arena_payload = json.loads(Path(args.arena_file).read_text(encoding="utf-8"))
    else:
        try:
            arena_payload = fetch_json(f"{api_base}/arena/state", headers, args.timeout)
        except Exception as exc:
            print(f"[metrics] Error al consultar /arena/state: {exc}", file=sys.stderr)
            arena_payload = {}

    lines = build_metrics(pnl_payload, arena_payload)
    if not lines:
        print("[metrics] No se generaron métricas (verifica endpoints).", file=sys.stderr)
        return

    write_prom_file(Path(args.output), lines)
    print(f"[metrics] Escribió {len(lines)} métricas en {args.output}")


if __name__ == "__main__":
    main()
