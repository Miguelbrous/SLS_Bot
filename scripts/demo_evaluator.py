#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, Optional

try:
    from bot.config_loader import load_config  # type: ignore
except ImportError:
    from bot.sls_bot.config_loader import load_config  # type: ignore

from scripts.lib.demo_learning import (
    ActionPlan,
    EvaluatorThresholds,
    StrategyMetrics,
    append_ledger,
    compute_metrics,
    filter_by_lookback,
    load_demo_history,
    load_pnl_closes,
    match_trades,
    plan_actions,
    summarize,
    update_arena_registry,
    write_state,
)


def _resolve_logs_dir(explicit: Optional[Path] = None) -> Path:
    if explicit:
        return explicit.expanduser().resolve()
    cfg = load_config()
    paths = cfg.get("paths") if isinstance(cfg, dict) else {}
    raw = (paths or {}).get("logs_dir")
    root = Path(__file__).resolve().parents[1]
    if isinstance(raw, str) and raw:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = (root / candidate).resolve()
        return candidate
    return (root / "logs").resolve()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Loop de evaluación demo -> calcula métricas reales y genera guardrails automáticos"
    )
    parser.add_argument("--logs-dir", type=Path, default=None, help="Directorio base de logs (default: config.paths.logs_dir)")
    parser.add_argument("--history", type=Path, default=None, help="Ruta a demo_emitter_history.jsonl")
    parser.add_argument("--pnl", type=Path, default=None, help="Ruta a pnl.jsonl del modo demo")
    parser.add_argument("--state-path", type=Path, default=None, help="Ruta destino para estado JSON")
    parser.add_argument("--ledger-path", type=Path, default=None, help="Ruta destino para ledger JSONL")
    parser.add_argument("--lookback-hours", type=float, default=72.0, help="Ventana (horas) para evaluar (default 72h)")
    parser.add_argument("--min-trades", type=int, default=15, help="Trades mínimos antes de tomar decisiones")
    parser.add_argument("--min-win-rate", type=float, default=45.0)
    parser.add_argument("--min-sharpe", type=float, default=0.2)
    parser.add_argument("--max-drawdown", type=float, default=8.0)
    parser.add_argument("--boost-win-rate", type=float, default=65.0)
    parser.add_argument("--boost-sharpe", type=float, default=0.7)
    parser.add_argument("--risk-step", type=float, default=0.2)
    parser.add_argument("--min-risk-multiplier", type=float, default=0.25)
    parser.add_argument("--max-risk-multiplier", type=float, default=1.6)
    parser.add_argument("--dry-run", action="store_true", help="No escribe estado/ledger ni toca la arena")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logs_dir = _resolve_logs_dir(args.logs_dir)
    history_path = args.history or (logs_dir / "demo_emitter_history.jsonl")
    pnl_path = args.pnl or (logs_dir / "pnl.jsonl")
    state_path = args.state_path or (logs_dir / "demo_learning_state.json")
    ledger_path = args.ledger_path or (logs_dir / "demo_learning_ledger.jsonl")

    decisions = load_demo_history(history_path)
    closes = load_pnl_closes(pnl_path)
    decisions, closes = filter_by_lookback(decisions, closes, args.lookback_hours)
    trades, match_summary = match_trades(decisions, closes)
    if not trades:
        print("[demo-evaluator] No hay trades cerrados en la ventana seleccionada.")
        return 0

    metrics = compute_metrics(trades)
    thresholds = EvaluatorThresholds(
        min_trades=args.min_trades,
        min_win_rate=args.min_win_rate,
        min_sharpe=args.min_sharpe,
        max_drawdown_pct=args.max_drawdown,
        boost_win_rate=args.boost_win_rate,
        boost_sharpe=args.boost_sharpe,
        min_risk_multiplier=args.min_risk_multiplier,
        max_risk_multiplier=args.max_risk_multiplier,
        risk_step=args.risk_step,
    )
    plans = plan_actions(metrics, thresholds)
    summary_meta = summarize(trades, metrics, match_summary)
    summary_meta["lookback_hours"] = args.lookback_hours

    if not args.dry_run:
        write_state(state_path, metrics=metrics, plans=plans, thresholds=thresholds, meta=summary_meta)
        for strategy_id, metric in metrics.items():
            plan = plans.get(strategy_id)
            if plan:
                append_ledger(ledger_path, strategy_id=strategy_id, metrics=metric, plan=plan)
        arena_meta = update_arena_registry(metrics)
    else:
        arena_meta = {"updated": 0, "missing": []}
    summary_meta["arena_updates"] = arena_meta

    _print_summary(metrics, plans, summary_meta)
    return 0


def _print_summary(metrics: Dict[str, "StrategyMetrics"], plans: Dict[str, "ActionPlan"], summary: Dict[str, object]) -> None:  # type: ignore[name-defined]
    print("[demo-evaluator] Estrategias evaluadas:", len(metrics))
    for strategy_id, metric in metrics.items():
        plan = plans.get(strategy_id)
        data = metric.to_dict()
        win_rate = data.get("win_rate", 0.0)
        sharpe = data.get("sharpe_ratio", 0.0)
        trades = data.get("trades", 0)
        dd = data.get("max_drawdown_pct", 0.0)
        action = plan.action if plan else "n/a"
        mult = plan.risk_multiplier if plan else "-"
        print(
            f" - {strategy_id}: trades={trades} win_rate={win_rate:.1f}% sharpe={sharpe:.2f} "
            f"dd={dd:.2f}% -> action={action} (x{mult})"
        )
    print("[demo-evaluator] Resumen:", summary)


if __name__ == "__main__":
    sys.exit(main())
