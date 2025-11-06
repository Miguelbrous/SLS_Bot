#!/usr/bin/env python3
"""
Dispara una ingesta puntual del Cerebro y guarda los resultados en disco.
Permite validar las fuentes (market/news/macro/orderflow) sin levantar todo el servicio.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime
from pathlib import Path
from collections import defaultdict
from typing import Dict, List

import requests

ROOT = Path(__file__).resolve().parents[2]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.cerebro.config import load_cerebro_config
from bot.cerebro.ingestion import DataIngestionManager, IngestionTask


class IngestValidationError(RuntimeError):
    """Se lanza cuando faltan fuentes obligatorias."""


def _csv(value: str | None) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingesta puntual de data sources del Cerebro.")
    parser.add_argument("--symbols", help="Lista separada por comas (override de config).", default="")
    parser.add_argument("--timeframes", help="Lista separada por comas (override de config).", default="")
    parser.add_argument("--market-limit", type=int, default=200, help="Velas por símbolo/timeframe.")
    parser.add_argument("--news-limit", type=int, default=50, help="Noticias máximas a consultar.")
    parser.add_argument("--macro-limit", type=int, default=20, help="Entradas macro que se conservarán.")
    parser.add_argument("--max-tasks", type=int, default=50, help="Límite de tareas procesadas en esta corrida.")
    parser.add_argument("--output", default="tmp_logs/cerebro_ingestion.json", help="Archivo JSON destino.")
    parser.add_argument("--include-news", action="store_true", help="Forzar consulta de feeds RSS.")
    parser.add_argument("--include-macro", action="store_true", help="Forzar consulta de feeds macro.")
    parser.add_argument("--include-orderflow", action="store_true", help="Forzar lectura de orderflow aunque esté deshabilitado en config.")
    parser.add_argument("--include-funding", action="store_true", help="Consulta funding aunque esté deshabilitado en config.")
    parser.add_argument("--include-onchain", action="store_true", help="Consulta on-chain aunque esté deshabilitado en config.")
    parser.add_argument("--funding-symbols", help="Lista separada por comas para funding (default = symbols).", default="")
    parser.add_argument("--onchain-symbols", help="Lista separada por comas para on-chain (default = symbols).", default="")
    parser.add_argument("--require-sources", help="Lista separada por comas (market,news,macro,orderflow,funding,onchain) que deben devolver filas.", default="")
    parser.add_argument("--min-market-rows", type=int, default=0, help="Mínimo de velas obtenidas para aprobar la ingesta (sumando todos los símbolos/timeframes).")
    parser.add_argument("--slack-webhook", help="Webhook opcional para notificar resultados (OK/ERROR)")
    return parser


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def run(args: argparse.Namespace) -> Dict[str, dict]:
    cfg = load_cerebro_config()
    symbols = _csv(args.symbols) or list(cfg.symbols)
    timeframes = _csv(args.timeframes) or list(cfg.timeframes)
    funding_symbols = _csv(args.funding_symbols) or symbols
    onchain_symbols = _csv(args.onchain_symbols) or symbols

    manager = DataIngestionManager(
        news_feeds=cfg.news_feeds,
        cache_ttl=cfg.data_cache_ttl,
        macro_config=cfg.macro_feeds,
        orderflow_config=cfg.orderflow_feeds,
        funding_config=cfg.funding_feeds,
        onchain_config=cfg.onchain_feeds,
    )
    manager.warmup(symbols, timeframes)

    # NPR: schedule additional feeds.
    if args.include_news and cfg.news_feeds:
        manager.schedule(IngestionTask(source="news", limit=max(1, args.news_limit)))
    if args.include_macro:
        manager.schedule(IngestionTask(source="macro", limit=max(1, args.macro_limit)))
    orderflow_enabled = bool((cfg.orderflow_feeds or {}).get("enabled"))
    if args.include_orderflow or orderflow_enabled:
        for symbol in symbols:
            manager.schedule(IngestionTask(source="orderflow", symbol=symbol, timeframe=timeframes[0] if timeframes else None, limit=1))
    funding_enabled = bool((cfg.funding_feeds or {}).get("enabled"))
    if args.include_funding or funding_enabled:
        for symbol in funding_symbols:
            manager.schedule(IngestionTask(source="funding", symbol=symbol, limit=1))
    onchain_enabled = bool((cfg.onchain_feeds or {}).get("enabled"))
    if args.include_onchain or onchain_enabled:
        for symbol in onchain_symbols:
            manager.schedule(IngestionTask(source="onchain", symbol=symbol, limit=1))

    results = manager.run_pending(max_tasks=max(1, args.max_tasks))
    summary = _build_summary(results)
    _validate_requirements(summary, args.require_sources, args.min_market_rows)
    payload = {
        "ts": int(time.time()),
        "symbols": symbols,
        "timeframes": timeframes,
        "news_feeds": cfg.news_feeds,
        "macro_feeds": cfg.macro_feeds,
        "orderflow_enabled": orderflow_enabled or args.include_orderflow,
        "funding_enabled": funding_enabled or args.include_funding,
        "onchain_enabled": onchain_enabled or args.include_onchain,
        "funding_symbols": funding_symbols,
        "onchain_symbols": onchain_symbols,
        "results": results,
        "summary": summary,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    print(f"[cerebro.ingest] Guardado {output_path} con {len(results)} tareas.")
    for source, count in summary["rows_by_source"].items():
        print(f"[cerebro.ingest] {source}: {count} filas")
    return summary


def _build_summary(results: Dict[str, List[dict]]) -> Dict[str, dict]:
    rows_by_source: Dict[str, int] = defaultdict(int)
    for key, entries in results.items():
        source = key.split(":", 1)[0]
        rows_by_source[source] += len(entries or [])
    return {"rows_by_source": dict(rows_by_source)}


def _validate_requirements(summary: Dict[str, dict], require_sources: str, min_market_rows: int) -> None:
    rows_by_source: Dict[str, int] = summary.get("rows_by_source", {})
    required = {item.strip().lower() for item in (require_sources or "").split(",") if item.strip()}
    if required:
        missing = {src for src in required if rows_by_source.get(src, 0) <= 0}
        if missing:
            raise IngestValidationError(
                f"Las fuentes requeridas no devolvieron filas: {', '.join(sorted(missing))}"
            )
    if min_market_rows > 0 and rows_by_source.get("market", 0) < min_market_rows:
        raise IngestValidationError(
            f"Solo se obtuvieron {rows_by_source.get('market', 0)} filas de market (<{min_market_rows})."
        )


def _format_slack_message(summary: Dict[str, dict], output: str, success: bool = True) -> str:
    rows = summary.get("rows_by_source", {})
    stats = ", ".join(f"{src}={count}" for src, count in sorted(rows.items())) or "sin datos"
    status = ":white_check_mark:" if success else ":x:"
    return f"{status} Cerebro ingest ({Path(output).name}): {stats}"


def _post_slack(webhook: str, text: str) -> None:
    try:
        resp = requests.post(webhook, json={"text": text}, timeout=5)
        resp.raise_for_status()
    except Exception as exc:
        print(f"[cerebro.ingest] No se pudo notificar a Slack: {exc}", file=sys.stderr)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        summary = run(args)
        if args.slack_webhook:
            _post_slack(args.slack_webhook, _format_slack_message(summary, args.output, success=True))
    except IngestValidationError as exc:
        if getattr(args, "slack_webhook", None):
            _post_slack(args.slack_webhook, f":x: Cerebro ingest falló: {exc}")
        raise SystemExit(f"[cerebro.ingest] {exc}") from exc
    except Exception as exc:
        if getattr(args, "slack_webhook", None):
            _post_slack(args.slack_webhook, f":x: Cerebro ingest error inesperado: {exc}")
        raise


if __name__ == "__main__":
    main()
