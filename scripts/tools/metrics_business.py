#!/usr/bin/env python3
"""
Genera métricas de negocio (PnL, drawdown, win rate, etc.) en formato Prometheus (textfile).

Uso típico:

    python scripts/tools/metrics_business.py --mode real --output metrics/business.prom

Luego basta con apuntar el textfile collector de Node Exporter a ese archivo
o moverlo a /var/lib/node_exporter/textfile_collector/.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import pstdev
from typing import Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "bot"))

from sls_bot.config_loader import load_config  # type: ignore  # noqa: E402


@dataclass
class TradeEntry:
    ts: datetime
    pnl: float
    symbol: str
    before: float | None
    after: float | None


@dataclass
class DailyEntry:
    ts: datetime
    pnl_eur: float
    pnl_pct: float | None
    trades: int | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Construye métricas de negocio a partir de logs/pnl.jsonl.")
    parser.add_argument("--mode", default=None, help="SLSBOT_MODE a usar (sobre-escribe config).")
    parser.add_argument("--config", type=Path, default=None, help="Ruta manual a config.json.")
    parser.add_argument("--logs-dir", type=Path, default=None, help="Sobrescribe paths.logs_dir.")
    parser.add_argument("--pnl-log", type=Path, default=None, help="Archivo pnl.jsonl (por defecto logs_dir/pnl.jsonl).")
    parser.add_argument("--output", type=Path, required=True, help="Archivo .prom de salida.")
    parser.add_argument("--lookback-days", type=int, default=30, help="Ventana para métricas agregadas.")
    parser.add_argument("--daily-limit", type=int, default=14, help="Cuántos días recientes exportar.")
    parser.add_argument("--stdout", action="store_true", help="Imprime también el payload generado.")
    return parser.parse_args()


def _parse_ts(value: object) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (float, int)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None
    if isinstance(value, str):
        txt = value.strip()
        if not txt:
            return None
        if txt.endswith("Z"):
            txt = txt[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(txt)
        except Exception:
            return None
    return None


def _sanitize_float(value: object) -> float:
    try:
        num = float(value)
    except Exception:
        return 0.0
    if math.isnan(num) or math.isinf(num):
        return 0.0
    return num


def _load_pnl_entries(path: Path) -> List[dict]:
    if not path.exists():
        return []
    entries: List[dict] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entries.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue
    except Exception:
        return []
    return entries


def _resolve_logs_dir(cfg: dict, args: argparse.Namespace) -> Path:
    if args.logs_dir:
        return args.logs_dir
    logs_dir = cfg.get("paths", {}).get("logs_dir")
    if not logs_dir:
        logs_dir = REPO_ROOT / "logs"
    return Path(logs_dir)


def _collect_entries(entries: Sequence[dict], cutoff: datetime) -> Tuple[List[TradeEntry], List[DailyEntry]]:
    trades: List[TradeEntry] = []
    daily: List[DailyEntry] = []
    for row in entries:
        ts = _parse_ts(row.get("ts"))
        if not ts and row.get("day"):
            ts = _parse_ts(f"{row['day']}T00:00:00Z")
        if not ts or ts < cutoff:
            continue
        entry_type = (row.get("type") or "close").lower()
        if entry_type == "daily":
            daily.append(
                DailyEntry(
                    ts=ts,
                    pnl_eur=_sanitize_float(row.get("pnl_eur") or row.get("pnl")),
                    pnl_pct=_sanitize_float(row.get("pnl_pct")) if row.get("pnl_pct") is not None else None,
                    trades=int(row.get("trades")) if row.get("trades") is not None else None,
                )
            )
            continue
        trades.append(
            TradeEntry(
                ts=ts,
                pnl=_sanitize_float(row.get("pnl") or row.get("pnl_eur")),
                symbol=str(row.get("symbol") or "UNKNOWN").upper(),
                before=_sanitize_float(row.get("before")) if row.get("before") is not None else None,
                after=_sanitize_float(row.get("after")) if row.get("after") is not None else None,
            )
        )
    trades.sort(key=lambda item: item.ts)
    daily.sort(key=lambda item: item.ts)
    return trades, daily


class PrometheusWriter:
    def __init__(self) -> None:
        self.lines: List[str] = []
        self._described: set[str] = set()

    def add(self, name: str, value: float, *, labels: Dict[str, str] | None = None,
            help_text: str | None = None, metric_type: str = "gauge") -> None:
        if help_text and name not in self._described:
            self.lines.append(f"# HELP {name} {help_text}")
        if metric_type and name not in self._described:
            self.lines.append(f"# TYPE {name} {metric_type}")
        self._described.add(name)
        labels_str = ""
        if labels:
            escaped = [
                f'{k}="{str(v).replace("\\\\", "\\\\\\\\").replace("\"", "\\\"")}"'
                for k, v in sorted(labels.items())
            ]
            labels_str = "{" + ",".join(escaped) + "}"
        self.lines.append(f"{name}{labels_str} {value:.10f}")

    def render(self) -> str:
        return "\n".join(self.lines) + "\n"


def _seconds_between(now: datetime, ts: Optional[datetime]) -> float:
    if not ts:
        return 0.0
    return max(0.0, (now - ts).total_seconds())


def compute_metrics(trades: Sequence[TradeEntry], daily: Sequence[DailyEntry], *, now: datetime) -> dict:
    trades_count = len(trades)
    pnl_values = [trade.pnl for trade in trades]
    pnl_total = sum(pnl_values)
    wins = sum(1 for value in pnl_values if value > 0)
    losses = sum(1 for value in pnl_values if value < 0)
    ties = trades_count - wins - losses
    win_rate = (wins / trades_count) if trades_count else 0.0
    avg_pnl = (pnl_total / trades_count) if trades_count else 0.0
    pnl_std = pstdev(pnl_values) if len(pnl_values) >= 2 else 0.0

    symbol_pnl: Dict[str, float] = defaultdict(float)
    symbol_trades: Dict[str, int] = defaultdict(int)
    equity_peak = 0.0
    max_drawdown_pct = 0.0
    for trade in trades:
        symbol_pnl[trade.symbol] += trade.pnl
        symbol_trades[trade.symbol] += 1
        before = trade.before if trade.before and trade.before > 0 else None
        after = trade.after if trade.after and trade.after > 0 else None
        reference = after or before
        if reference is None or reference <= 0:
            continue
        if reference > equity_peak:
            equity_peak = reference
        if equity_peak > 0 and after:
            dd_pct = ((equity_peak - after) / equity_peak) * 100
            max_drawdown_pct = max(max_drawdown_pct, dd_pct)

    last_trade_ts = trades[-1].ts if trades else None
    last_daily_ts = daily[-1].ts if daily else None

    metrics = {
        "trades_total": trades_count,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "win_rate": win_rate,
        "pnl_total": pnl_total,
        "pnl_avg": avg_pnl,
        "pnl_std": pnl_std,
        "max_drawdown_pct": max_drawdown_pct,
        "last_trade_ts": last_trade_ts,
        "last_daily_ts": last_daily_ts,
        "last_trade_age_seconds": _seconds_between(now, last_trade_ts),
        "last_daily_age_seconds": _seconds_between(now, last_daily_ts),
        "symbol_pnl": dict(symbol_pnl),
        "symbol_trades": dict(symbol_trades),
        "daily": list(daily),
    }
    return metrics


def write_metrics(metrics: dict, *, writer: PrometheusWriter, mode: str, now: datetime, daily_limit: int) -> None:
    labels = {"mode": mode}
    writer.add("sls_bot_business_trades_total", metrics["trades_total"], labels=labels,
               help_text="Cantidad de trades registrados en la ventana.")
    writer.add("sls_bot_business_wins_total", metrics["wins"], labels=labels)
    writer.add("sls_bot_business_losses_total", metrics["losses"], labels=labels)
    writer.add("sls_bot_business_ties_total", metrics["ties"], labels=labels)
    writer.add("sls_bot_business_win_rate", metrics["win_rate"], labels=labels,
               help_text="Win rate (0-1) en la ventana.")
    writer.add("sls_bot_business_pnl_total_eur", metrics["pnl_total"], labels=labels,
               help_text="PnL acumulado en moneda base.")
    writer.add("sls_bot_business_avg_trade_eur", metrics["pnl_avg"], labels=labels,
               help_text="PnL medio por trade.")
    writer.add("sls_bot_business_pnl_std_eur", metrics["pnl_std"], labels=labels,
               help_text="Desvío estándar del PnL por trade.")
    writer.add("sls_bot_business_max_drawdown_pct", metrics["max_drawdown_pct"], labels=labels,
               help_text="Drawdown máximo estimado (porcentaje).")

    last_trade_ts = metrics["last_trade_ts"]
    writer.add("sls_bot_business_last_trade_timestamp", last_trade_ts.timestamp() if last_trade_ts else 0.0,
               labels=labels, help_text="Último trade (epoch).")
    writer.add("sls_bot_business_last_trade_age_seconds", metrics["last_trade_age_seconds"], labels=labels,
               help_text="Segundos desde el último trade.")

    last_daily_ts = metrics["last_daily_ts"]
    writer.add("sls_bot_business_last_daily_summary_timestamp",
               last_daily_ts.timestamp() if last_daily_ts else 0.0,
               labels=labels, help_text="Último resumen diario (epoch).")
    writer.add("sls_bot_business_last_daily_summary_age_seconds", metrics["last_daily_age_seconds"],
               labels=labels, help_text="Segundos desde el último resumen diario.")

    for symbol, pnl in sorted(metrics["symbol_pnl"].items()):
        writer.add("sls_bot_business_pnl_symbol_eur", pnl, labels={**labels, "symbol": symbol})
    for symbol, count in sorted(metrics["symbol_trades"].items()):
        writer.add("sls_bot_business_trades_symbol_total", count, labels={**labels, "symbol": symbol})

    daily_entries: List[DailyEntry] = metrics["daily"]
    recent_daily = daily_entries[-max(1, daily_limit):]
    for entry in recent_daily:
        day_label = entry.ts.strftime("%Y-%m-%d")
        writer.add("sls_bot_business_daily_pnl_eur", entry.pnl_eur,
                   labels={**labels, "day": day_label},
                   help_text="PnL diario reportado por /daily/summary.")
        if entry.pnl_pct is not None:
            writer.add("sls_bot_business_daily_pnl_pct", entry.pnl_pct, labels={**labels, "day": day_label})
        if entry.trades is not None:
            writer.add("sls_bot_business_daily_trades", float(entry.trades), labels={**labels, "day": day_label})

    writer.add("sls_bot_business_snapshot_timestamp", now.timestamp(), labels=labels,
               help_text="Momento en que se calcularon estas métricas.")


def main() -> None:
    args = parse_args()
    if args.mode:
        os.environ["SLSBOT_MODE"] = args.mode
    if args.config:
        os.environ["SLSBOT_CONFIG"] = str(args.config)
    else:
        if not os.getenv("SLSBOT_CONFIG"):
            default_cfg = REPO_ROOT / "config" / "config.json"
            sample_cfg = default_cfg.with_name("config.sample.json")
            if not default_cfg.exists() and sample_cfg.exists():
                os.environ["SLSBOT_CONFIG"] = str(sample_cfg)

    cfg = load_config()
    mode = cfg.get("_active_mode") or args.mode or "unknown"
    logs_dir = _resolve_logs_dir(cfg, args)
    pnl_path = args.pnl_log or (logs_dir / "pnl.jsonl")

    entries = _load_pnl_entries(pnl_path)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max(1, args.lookback_days))
    trades, daily = _collect_entries(entries, cutoff)
    metrics = compute_metrics(trades, daily, now=now)

    writer = PrometheusWriter()
    write_metrics(metrics, writer=writer, mode=mode, now=now, daily_limit=args.daily_limit)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = writer.render()
    args.output.write_text(payload, encoding="utf-8")
    if args.stdout:
        print(payload, end="")


if __name__ == "__main__":
    main()
