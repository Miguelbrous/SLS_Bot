#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests
from requests.auth import HTTPBasicAuth

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_STATE_PATH = ROOT_DIR / "logs" / "demo_learning_state.json"
PROMOTION_LOG = ROOT_DIR / "logs" / "promotions" / "demo_to_real.jsonl"
OPS_PATH = ROOT_DIR / "scripts" / "ops.py"


def _load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"No se encontró {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _get_strategy_entry(state: Dict[str, Any], strategy_id: str) -> Dict[str, Any]:
    strategies = state.get("strategies") or {}
    entry = strategies.get(strategy_id)
    if not entry:
        raise KeyError(f"{strategy_id} no está presente en demo_learning_state.json")
    return entry


def _validate_metrics(metrics: Dict[str, Any], plan: Dict[str, Any] | None, args: argparse.Namespace) -> List[str]:
    issues: List[str] = []
    trades = float(metrics.get("trades") or 0)
    win_rate = float(metrics.get("win_rate") or 0.0)
    sharpe = float(metrics.get("sharpe_ratio") or 0.0)
    drawdown = float(metrics.get("max_drawdown_pct") or 0.0)

    if trades < args.min_trades:
        issues.append(f"Trades insuficientes ({trades} < {args.min_trades})")
    if win_rate < args.min_win_rate:
        issues.append(f"Win rate {win_rate:.2f}% < {args.min_win_rate}%")
    if sharpe < args.min_sharpe:
        issues.append(f"Sharpe {sharpe:.2f} < {args.min_sharpe}")
    if drawdown > args.max_drawdown:
        issues.append(f"Drawdown {drawdown:.2f}% > {args.max_drawdown}%")
    if plan and plan.get("action") == "disable":
        issues.append("Plan vigente = disable (demo_evaluator bloqueó la estrategia)")
    return issues


def _run_ops_promote(strategy_id: str, args: argparse.Namespace) -> None:
    cmd: List[str] = [
        sys.executable,
        str(OPS_PATH),
        "arena",
        "promote-real",
        strategy_id,
        "--min-trades",
        str(args.arena_min_trades or args.min_trades),
        "--min-sharpe",
        str(args.arena_min_sharpe or args.min_sharpe),
        "--max-drawdown",
        str(args.arena_max_drawdown or args.max_drawdown),
        "--source-mode",
        args.source_mode,
        "--target-mode",
        args.target_mode,
        "--min-auc",
        str(args.min_auc),
        "--min-win-rate",
        str(args.min_real_win_rate),
    ]
    if args.output_dir:
        cmd.extend(["--output-dir", str(args.output_dir)])
    if args.force:
        cmd.append("--force")
    if args.skip_dataset_rotation:
        cmd.append("--skip-dataset-rotation")
    subprocess.run(cmd, check=True)


def _append_promotion_log(payload: Dict[str, Any]) -> None:
    PROMOTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with PROMOTION_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _trigger_control(args: argparse.Namespace) -> Tuple[bool, str]:
    if not args.control_api or not args.control_user or not args.control_password:
        return False, "control API no configurada"
    url = f"{args.control_api.rstrip('/')}/control/{args.control_service}/{args.control_action}"
    resp = requests.post(url, auth=HTTPBasicAuth(args.control_user, args.control_password), timeout=15)
    if resp.status_code >= 300:
        raise RuntimeError(f"Control API respondió {resp.status_code}: {resp.text[:200]}")
    detail = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
    return True, str(detail)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promueve estrategias demo→real usando métricas vivas")
    parser.add_argument("strategy_id")
    parser.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--output-dir", type=Path, default=None, help="Directorio destino del paquete")
    parser.add_argument("--min-trades", type=int, default=40, help="Trades mínimos permitidos en demo")
    parser.add_argument("--min-win-rate", type=float, default=55.0)
    parser.add_argument("--min-sharpe", type=float, default=0.35)
    parser.add_argument("--max-drawdown", type=float, default=6.0, help="Drawdown máximo permitido (%)")
    parser.add_argument("--arena-min-trades", type=int, default=None, help="Override para ops arena --min-trades")
    parser.add_argument("--arena-min-sharpe", type=float, default=None)
    parser.add_argument("--arena-max-drawdown", type=float, default=None)
    parser.add_argument("--source-mode", default="demo")
    parser.add_argument("--target-mode", default="real")
    parser.add_argument("--min-auc", type=float, default=0.60)
    parser.add_argument("--min-real-win-rate", type=float, default=0.57)
    parser.add_argument("--skip-dataset-rotation", action="store_true")
    parser.add_argument("--force", action="store_true", help="Ignora validaciones mínimas")
    parser.add_argument("--dry-run", action="store_true", help="Sólo imprime el resumen, no ejecuta promoción")
    parser.add_argument("--control-api", help="URL base del API real (ej. https://api.mi-vps)")
    parser.add_argument("--control-service", default="sls-bot", help="Servicio a reiniciar vía /control/*")
    parser.add_argument("--control-action", default="restart", help="Acción systemctl (start/stop/restart)")
    parser.add_argument("--control-user", help="Usuario Basic Auth para /control/*")
    parser.add_argument("--control-password", help="Contraseña Basic Auth")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        state = _load_state(args.state_path)
    except FileNotFoundError as exc:
        print(f"[demo-promote] {exc}", file=sys.stderr)
        return 1
    try:
        entry = _get_strategy_entry(state, args.strategy_id)
    except KeyError as exc:
        print(f"[demo-promote] {exc}", file=sys.stderr)
        return 1
    metrics = entry.get("metrics") or {}
    plan = entry.get("plan") or {}

    issues = [] if args.force else _validate_metrics(metrics, plan, args)
    if issues:
        print("[demo-promote] Estrategia no cumple los requisitos:")
        for idx, issue in enumerate(issues, start=1):
            print(f"  {idx}. {issue}")
        return 2

    trades_val = metrics.get("trades")
    win_rate_val = float(metrics.get("win_rate") or 0.0)
    sharpe_val = float(metrics.get("sharpe_ratio") or 0.0)
    drawdown_val = float(metrics.get("max_drawdown_pct") or 0.0)
    plan_action = plan.get("action", "unknown")
    plan_multiplier = plan.get("risk_multiplier", "-")
    print(
        f"[demo-promote] Métricas actuales {args.strategy_id}: trades={trades_val} "
        f"win_rate={win_rate_val:.2f}% sharpe={sharpe_val:.2f} drawdown={drawdown_val:.2f}%"
    )
    print(f"[demo-promote] Acción recomendada: {plan_action} (x{plan_multiplier})")

    if args.dry_run:
        print("[demo-promote] Dry-run activo; no se ejecutan pasos posteriores.")
        return 0

    try:
        _run_ops_promote(args.strategy_id, args)
    except subprocess.CalledProcessError as exc:
        print(f"[demo-promote] Error ejecutando ops.py arena promote-real: {exc}", file=sys.stderr)
        return exc.returncode or 1

    log_payload = {
        "ts": int(time.time()),
        "strategy_id": args.strategy_id,
        "metrics": metrics,
        "plan": plan,
        "thresholds": {
            "min_trades": args.min_trades,
            "min_win_rate": args.min_win_rate,
            "min_sharpe": args.min_sharpe,
            "max_drawdown": args.max_drawdown,
            "min_auc": args.min_auc,
            "min_real_win_rate": args.min_real_win_rate,
        },
        "ops": {
            "output_dir": str(args.output_dir) if args.output_dir else None,
            "source_mode": args.source_mode,
            "target_mode": args.target_mode,
        },
    }
    _append_promotion_log(log_payload)
    print(f"[demo-promote] Registro actualizado en {PROMOTION_LOG}")

    if args.control_api:
        try:
            _, detail = _trigger_control(args)
            print(f"[demo-promote] Control API ejecutado: {detail}")
        except Exception as exc:
            print(f"[demo-promote] Control API falló: {exc}", file=sys.stderr)
            return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
