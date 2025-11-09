#!/usr/bin/env python3
"""
Genera un resumen integral para el pipeline Autopilot/Arena 2V:
- Valida el dataset de experiencias (stats básicos).
- Rankea los candidatos (usando arena_rank).
- Opcionalmente escribe un JSON y avisa vía Slack.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable, List

import requests  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from bot.cerebro.dataset_utils import load_rows, summarize_rows  # noqa: E402
from scripts.tools import arena_rank  # noqa: E402


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resumen Autopilot/Arena 2V.")
    parser.add_argument("--dataset", type=Path, required=True, help="Ruta al cerebro_experience.jsonl.")
    parser.add_argument("--runs", nargs="+", type=Path, required=True, help="Archivos/carpeta con resultados de Arena/autopilot.")
    parser.add_argument("--min-trades", type=int, default=80)
    parser.add_argument("--max-drawdown", type=float, default=5.0)
    parser.add_argument("--max-drift", type=float, default=0.2)
    parser.add_argument("--require-symbols", type=str, default="BTCUSDT,ETHUSDT")
    parser.add_argument("--dataset-min-rows", type=int, default=150)
    parser.add_argument("--dataset-min-win-rate", type=float, default=0.45)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument("--prometheus-file", type=Path, default=None)
    parser.add_argument("--slack-webhook", type=str, default=os.getenv("SLACK_WEBHOOK_AUTOPILOT"))
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(list(argv) if argv is not None else None)


def dataset_health(dataset: Path, min_rows: int, min_win: float, require_symbols: List[str]) -> dict:
    rows = load_rows(dataset)
    summary = summarize_rows(rows)
    violations = []
    if summary["total"] < min_rows:
        violations.append(f"min_rows({summary['total']}<{min_rows})")
    if summary["win_rate"] < min_win:
        violations.append(f"win_rate({summary['win_rate']:.2f}<{min_win:.2f})")
    missing = [s for s in require_symbols if s and s not in summary["symbols"]]
    if missing:
        violations.append(f"missing_symbols({','.join(missing)})")
    return {"summary": summary, "violations": violations, "dataset": str(dataset)}


def autopilot_summary(args: argparse.Namespace) -> dict:
    dataset_report = dataset_health(
        args.dataset,
        args.dataset_min_rows,
        args.dataset_min_win_rate,
        [s.strip().upper() for s in args.require_symbols.split(",") if s.strip()],
    )
    ranking_args = SimpleNamespace(
        min_trades=args.min_trades,
        max_drawdown=args.max_drawdown,
        max_drift=args.max_drift,
        target_sharpe=1.6,
        target_calmar=2.0,
        target_profit_factor=1.8,
        target_win_rate=0.55,
        target_drawdown=4.0,
    )
    ranking = arena_rank.rank_candidates(args.runs, ranking_args)
    return {
        "dataset": dataset_report,
        "arena": ranking,
    }


def post_slack(webhook: str, payload: dict, top: int) -> None:
    dataset = payload["dataset"]
    arena = payload["arena"]
    status = "✅" if not dataset["violations"] and arena["accepted"] else "⚠️"
    text = [
        f"{status} Autopilot summary",
        f"Dataset: {dataset['dataset'] if 'dataset' in dataset else ''}",
        f"- rows: {dataset['summary']['total']} / win_rate: {dataset['summary']['win_rate']:.2f}",
    ]
    if dataset["violations"]:
        text.append(f"- violations: {', '.join(dataset['violations'])}")
    if arena["accepted"]:
        text.append("Top candidates:")
        for rank, row in enumerate(arena["accepted"][:top], 1):
            stats = row["stats"]
            text.append(
                f"{rank}. {row['name']} score={row['score']:.2f} "
                f"Sharpe={stats['sharpe']:.2f} Calmar={stats['calmar']:.2f} "
                f"DD={stats['max_drawdown']:.2f}%"
            )
    else:
        text.append("No candidates accepted.")
    if arena["rejected"]:
        text.append(f"Rejected: {len(arena['rejected'])}")
    requests.post(webhook, json={"text": "\n".join(text)}, timeout=6)


def render_markdown(payload: dict, top: int) -> str:
    dataset = payload["dataset"]
    arena = payload["arena"]
    lines = [
        f"# Autopilot summary",
        "",
        "## Dataset",
        f"- rows: {dataset['summary']['total']}",
        f"- win_rate: {dataset['summary']['win_rate']:.3f}",
        f"- dominant_symbol_share: {dataset['summary']['dominant_symbol_share']:.3f}",
    ]
    if dataset["violations"]:
        lines.append(f"- violations: {', '.join(dataset['violations'])}")
    else:
        lines.append("- violations: none")
    lines.append("")
    lines.append("## Top candidates")
    if not arena["accepted"]:
        lines.append("_No candidates passed the guard rails._")
    else:
        lines.append("| Rank | Strategy | Score | Sharpe | Calmar | ProfitF | Win% | DD% | Trades | Drift |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for idx, row in enumerate(arena["accepted"][:top], 1):
            stats = row["stats"]
            lines.append(
                f"| {idx} | {row['name']} | {row['score']:.3f} | {stats['sharpe']:.2f} | {stats['calmar']:.2f} | "
                f"{stats['profit_factor']:.2f} | {stats['win_rate']*100:.1f}% | {stats['max_drawdown']:.2f}% | "
                f"{stats['trades']} | {stats.get('feature_drift', 0.0):.3f} |"
            )
    if arena["rejected"]:
        lines.append("")
        lines.append("## Rejected")
        for rej in arena["rejected"]:
            lines.append(f"- {rej['name']}: {', '.join(rej['violations'])}")
    return "\n".join(lines)


def render_prometheus(payload: dict) -> str:
    dataset = payload["dataset"]
    arena = payload["arena"]
    lines = [
        "# HELP sls_autopilot_dataset_rows Total rows in cerebro dataset",
        "# TYPE sls_autopilot_dataset_rows gauge",
        f"sls_autopilot_dataset_rows {dataset['summary']['total']}",
        "# HELP sls_autopilot_dataset_win_rate Win rate of dataset",
        "# TYPE sls_autopilot_dataset_win_rate gauge",
        f"sls_autopilot_dataset_win_rate {dataset['summary']['win_rate']:.4f}",
        "# HELP sls_autopilot_dataset_violations_count Number of dataset violations",
        "# TYPE sls_autopilot_dataset_violations_count gauge",
        f"sls_autopilot_dataset_violations_count {len(dataset['violations'])}",
        "# HELP sls_autopilot_candidates_total Number of accepted candidates",
        "# TYPE sls_autopilot_candidates_total gauge",
        f"sls_autopilot_candidates_total {len(arena['accepted'])}",
        "# HELP sls_autopilot_candidates_rejected Number of rejected candidates",
        "# TYPE sls_autopilot_candidates_rejected gauge",
        f"sls_autopilot_candidates_rejected {len(arena['rejected'])}",
    ]
    if arena["accepted"]:
        top = arena["accepted"][0]
        stats = top["stats"]
        lines.extend(
            [
                "# HELP sls_autopilot_top_score Score of top candidate",
                "# TYPE sls_autopilot_top_score gauge",
                f"sls_autopilot_top_score {top['score']:.4f}",
                "# HELP sls_autopilot_top_drawdown Drawdown of top candidate (%)",
                "# TYPE sls_autopilot_top_drawdown gauge",
                f"sls_autopilot_top_drawdown {stats['max_drawdown']:.4f}",
                "# HELP sls_autopilot_top_sharpe Sharpe ratio of top candidate",
                "# TYPE sls_autopilot_top_sharpe gauge",
                f"sls_autopilot_top_sharpe {stats['sharpe']:.4f}",
            ]
        )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    summary = autopilot_summary(args)
    if args.output_json:
        args.output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(render_markdown(summary, args.top), encoding="utf-8")
    if args.prometheus_file:
        args.prometheus_file.write_text(render_prometheus(summary), encoding="utf-8")
    if args.slack_webhook:
        post_slack(args.slack_webhook, summary, args.top)
    if args.json or not args.output_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
