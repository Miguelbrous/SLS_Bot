#!/usr/bin/env python3
"""
Pipeline CI para el autopilot del Cerebro.

1. Valida el dataset (filas, balance de pnl, símbolos, antigüedad).
2. Ejecuta `bot.cerebro.train` en modo dry-run y comprueba que las métricas superen los umbrales.
3. Opcionalmente envía un resumen a Slack y guarda un JSON con los resultados.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict

import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lib.cerebro_autopilot_dataset import (  # noqa: E402
    DatasetValidationError,
    analyze_dataset,
    ensure_dataset_quality,
)


def _extract_payload(stdout: str) -> Dict[str, object]:
    body = stdout.strip()
    if not body:
        raise RuntimeError("El entrenamiento no produjo salida.")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        start = body.find("{")
        end = body.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(body[start : end + 1])
    raise RuntimeError("No se pudo extraer el JSON de métricas del entrenamiento.")


def _post_slack(webhook: str, text: str, username: str | None = None) -> None:
    if not webhook:
        return
    try:
        payload = {"text": text}
        if username:
            payload["username"] = username
        resp = requests.post(webhook, json=payload, timeout=5)
        resp.raise_for_status()
    except Exception as exc:  # pragma: no cover
        print(f"[autopilot-ci] No se pudo notificar a Slack: {exc}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Valida dataset + dry-run del Cerebro autopilot (pensado para CI).")
    parser.add_argument("--mode", default="test", help="Modo a utilizar (default: test).")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Ruta al dataset de experiencias (default logs/<mode>/cerebro_experience.jsonl).",
    )
    parser.add_argument("--min-rows", type=int, default=200)
    parser.add_argument("--min-win-rate", type=float, default=0.3)
    parser.add_argument("--max-win-rate", type=float, default=0.8)
    parser.add_argument("--min-symbols", type=int, default=1)
    parser.add_argument("--max-age-hours", type=float, default=0.0, help="0 = no validar antigüedad.")
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--lr", type=float, default=0.05)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--min-ci-auc", type=float, default=0.52, help="AUC mínimo aceptado en CI.")
    parser.add_argument("--min-ci-win-rate", type=float, default=0.5, help="Win rate mínimo aceptado en CI.")
    parser.add_argument("--summary-json", help="Ruta opcional para escribir el resumen JSON.")
    parser.add_argument("--slack-webhook", help="Webhook opcional para notificar (éxito/fallo).")
    parser.add_argument("--slack-user", default="cerebro-autopilot-ci", help="Nombre de usuario para Slack.")
    return parser


def _run_train(
    mode: str,
    dataset: Path,
    *,
    epochs: int,
    lr: float,
    train_ratio: float,
) -> Dict[str, object]:
    cmd = [
        sys.executable,
        "-m",
        "bot.cerebro.train",
        "--mode",
        mode,
        "--dataset",
        str(dataset),
        "--epochs",
        str(epochs),
        "--lr",
        str(lr),
        "--train-ratio",
        str(train_ratio),
        "--dry-run",
        "--no-promote",
    ]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError("El entrenamiento dry-run falló.")
    return _extract_payload(result.stdout)


def format_slack_text(success: bool, mode: str, stats: Dict[str, object], metrics: Dict[str, float], reason: str | None) -> str:
    status = ":white_check_mark:" if success else ":x:"
    rows = stats.get("rows")
    auc = metrics.get("auc")
    win = metrics.get("win_rate")
    text = f"{status} Autopilot CI ({mode}) rows={rows}, auc={auc}, win={win}"
    if reason:
        text += f" :: {reason}"
    return text


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    dataset = args.dataset or (ROOT / "logs" / args.mode / "cerebro_experience.jsonl")
    dataset = dataset.expanduser()
    try:
        stats_obj = analyze_dataset(dataset)
        ensure_dataset_quality(
            stats_obj,
            min_rows=max(1, args.min_rows),
            min_win_rate=max(0.0, args.min_win_rate),
            max_win_rate=min(1.0, args.max_win_rate),
            min_symbols=max(1, args.min_symbols),
            max_age_hours=max(0.0, args.max_age_hours),
        )
        payload = _run_train(args.mode, dataset, epochs=args.epochs, lr=args.lr, train_ratio=args.train_ratio)
        metrics = payload.get("metrics") or {}
        auc = float(metrics.get("auc") or 0.0)
        win_rate = float(metrics.get("win_rate") or 0.0)
        success = auc >= args.min_ci_auc and win_rate >= args.min_ci_win_rate
        reason = None
        if not success:
            reason = f"auc={auc:.3f} (min {args.min_ci_auc}), win_rate={win_rate:.3f} (min {args.min_ci_win_rate})"
            raise DatasetValidationError(reason)
        summary = {
            "status": "ok",
            "dataset": stats_obj.to_dict(),
            "metrics": metrics,
            "mode": args.mode,
        }
    except DatasetValidationError as exc:
        summary = {
            "status": "error",
            "reason": str(exc),
            "dataset": stats_obj.to_dict() if "stats_obj" in locals() else {"path": str(dataset)},
            "mode": args.mode,
        }
        text = format_slack_text(False, args.mode, summary["dataset"], summary.get("metrics", {}), str(exc))
        if args.slack_webhook:
            _post_slack(args.slack_webhook, text, args.slack_user)
        if args.summary_json:
            Path(args.summary_json).parent.mkdir(parents=True, exist_ok=True)
            Path(args.summary_json).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        raise SystemExit(f"[autopilot-ci] {exc}") from exc
    else:
        text = format_slack_text(True, args.mode, summary["dataset"], summary["metrics"], None)
        if args.slack_webhook:
            _post_slack(args.slack_webhook, text, args.slack_user)
        output = json.dumps(summary, ensure_ascii=False, indent=2)
        print(output)
        if args.summary_json:
            Path(args.summary_json).parent.mkdir(parents=True, exist_ok=True)
            Path(args.summary_json).write_text(output, encoding="utf-8")


if __name__ == "__main__":
    main()
