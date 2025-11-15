#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.auth import HTTPBasicAuth

try:
    from bot.config_loader import CFG_PATH_IN_USE  # type: ignore
except ImportError:
    from bot.sls_bot.config_loader import CFG_PATH_IN_USE  # type: ignore

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_STATE_PATH = ROOT_DIR / "logs" / "demo_learning_state.json"
PROMOTION_LOG = ROOT_DIR / "logs" / "promotions" / "demo_to_real.jsonl"
OPS_PROMOTION_LOG = ROOT_DIR / "logs" / "promotions" / "promotion_log.jsonl"
OPS_PATH = ROOT_DIR / "scripts" / "ops.py"
CONFIG_FILE = Path(CFG_PATH_IN_USE).resolve() if CFG_PATH_IN_USE else None
CONFIG_SNAPSHOT = ROOT_DIR / "logs" / "promotions" / "config_snapshots"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _make_promotion_dir(strategy_id: str, base_dir: Optional[Path]) -> Path:
    stamp = _utc_now().strftime("%Y%m%d_%H%M%S")
    root = base_dir or (ROOT_DIR / "logs" / "promotions" / strategy_id)
    dest = root / stamp
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _snapshot_config(destination: Path, sources: List[Path]) -> Optional[Path]:
    try:
        snapshot_dir = destination / "snapshot"
        snapshot_dir.mkdir(exist_ok=True)
        files: List[Path] = []
        for src in sources:
            if not src:
                continue
            candidate = src if src.is_absolute() else (ROOT_DIR / src)
            if candidate.exists():
                dest = snapshot_dir / candidate.name
                dest.write_text(candidate.read_text(encoding="utf-8"), encoding="utf-8")
                files.append(dest)
        return snapshot_dir if files else None
    except Exception:
        return None


def _archive_package(package_path: Path, dest_dir: Path) -> Optional[Path]:
    if not package_path.exists():
        return None
    try:
        base = dest_dir / "package"
        archive = shutil.make_archive(str(base), "gztar", root_dir=package_path, base_dir=".")
        return Path(archive)
    except Exception:
        return None


def _run_internal_smoke(api_base: Optional[str], panel_token: Optional[str], control_user: Optional[str], control_password: Optional[str]) -> Tuple[int, str, str]:
    env = os.environ.copy()
    if api_base:
        env["SLS_API_BASE"] = api_base
    if panel_token:
        env["SLS_PANEL_TOKEN"] = panel_token
    if control_user:
        env["SLS_CONTROL_USER"] = control_user
    if control_password:
        env["SLS_CONTROL_PASSWORD"] = control_password
    cmd = [sys.executable, str(ROOT_DIR / "scripts" / "tests" / "e2e_smoke_real.py")]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return proc.returncode, proc.stdout, proc.stderr


def _tail_promotion_log(strategy_id: str) -> Optional[Dict[str, Any]]:
    if not OPS_PROMOTION_LOG.exists():
        return None
    try:
        lines = OPS_PROMOTION_LOG.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return None
    for raw in reversed(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        if payload.get("strategy_id") == strategy_id:
            return payload
    return None


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _render_checklist(strategy_id: str, ctx: Dict[str, Any], *, smoke_cmd: Optional[str], notes: Optional[str], qa_owner: Optional[str]) -> str:
    ts = ctx.get("timestamp")
    metrics = ctx.get("metrics") or {}
    plan = ctx.get("plan") or {}
    trades_val = metrics.get("trades")
    win_rate = float(metrics.get("win_rate") or 0.0)
    sharpe = float(metrics.get("sharpe_ratio") or 0.0)
    drawdown = float(metrics.get("max_drawdown_pct") or 0.0)
    plan_action = plan.get("action")
    plan_multiplier = plan.get("risk_multiplier")
    lines = [
        f"# Checklist promoción demo→real · {strategy_id}",
        "",
        f"- Fecha UTC: **{ts}**",
        f"- Responsable: **{qa_owner or 'ops'}**",
    ]
    if notes:
        lines.append(f"- Notas: {notes}")
    lines.extend(
        [
            "",
            "## Tareas",
            "- [x] Validaciones automáticas (métricas demo) ejecutadas por `scripts/demo_promote.py`.",
            "- [ ] QA manual: revisar paquete generado en `logs/promotions/` y validar configuración real.",
        ]
    )
    if smoke_cmd:
        lines.append(f"- [ ] Ejecutar smoke test real (`{smoke_cmd}`) y adjuntar salida en `smoke.log`.")
    else:
        lines.append("- [ ] Ejecutar smoke test real (`make smoke` o scripts/tests/e2e_smoke.py).")
    lines.extend(
        [
            "- [ ] Confirmar que el watchdog real y alertas Slack están en verde tras el reinicio.",
            "- [ ] Documentar la promoción en el runbook / Notion y avisar a trading.",
            "",
            "## Métricas demo utilizadas",
            f"- Trades: **{trades_val}**",
            f"- Win rate: **{win_rate:.2f}%**",
            f"- Sharpe: **{sharpe:.2f}**",
            f"- Max drawdown: **{drawdown:.2f}%**",
            f"- Acción recomendada por loop demo: **{plan_action}** (x{plan_multiplier})",
            "",
            "## Contexto adicional",
            f"- Control API ejecutado: **{ctx.get('control_executed')}** ({ctx.get('control_detail')})",
        ]
    )
    if ctx.get("smoke"):
        smoke = ctx["smoke"]
        lines.extend(
            [
                f"- Smoke test returncode: **{smoke.get('returncode')}**",
                "",
            ]
        )
    if ctx.get("ops_record"):
        entry = ctx["ops_record"]
        lines.extend(
            [
                "### Último registro en ops promotion log",
                f"- Paquete: `{entry.get('package')}`",
                f"- Modes: {entry.get('source_mode')} → {entry.get('target_mode')}",
                f"- Timestamp: {entry.get('ts')}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


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
    parser.add_argument("--artifact-dir", type=Path, default=None, help="Directorio raíz para guardar checklist/metadata")
    parser.add_argument("--smoke-cmd", help="Comando para ejecutar smoke test tras la promoción")
    parser.add_argument("--allow-smoke-fail", action="store_true", help="No aborta aunque el smoke falle")
    parser.add_argument("--auto-smoke", dest="auto_smoke", action="store_true", default=True, help="Ejecuta el smoke integrado e2e si no se pasa --smoke-cmd")
    parser.add_argument("--no-auto-smoke", dest="auto_smoke", action="store_false")
    parser.add_argument("--smoke-api-base", help="Override para SLS_API_BASE al ejecutar el smoke integrado")
    parser.add_argument("--smoke-panel-token", help="Override para SLS_PANEL_TOKEN")
    parser.add_argument("--smoke-control-user", help="Override para SLS_CONTROL_USER")
    parser.add_argument("--smoke-control-password", help="Override para SLS_CONTROL_PASSWORD")
    parser.add_argument("--qa-owner", help="Responsable que firmará el checklist")
    parser.add_argument("--notes", help="Notas adicionales para el checklist")
    parser.add_argument("--package-config", action="store_true", help="Incluye snapshot de config/demo_learning_state en la carpeta")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_path = args.state_path
    try:
        state = _load_state(state_path)
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
    context: Dict[str, Any] = {
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
        "timestamp": _utc_now().isoformat().replace("+00:00", "Z"),
        "control_executed": False,
        "control_detail": None,
        "state_path": str(state_path),
    }
    if CONFIG_FILE:
        context["config_file"] = str(CONFIG_FILE)

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

    promotion_dir: Optional[Path] = None
    try:
        _run_ops_promote(args.strategy_id, args)
    except subprocess.CalledProcessError as exc:
        print(f"[demo-promote] Error ejecutando ops.py arena promote-real: {exc}", file=sys.stderr)
        return exc.returncode or 1
    promotion_dir = _make_promotion_dir(args.strategy_id, args.artifact_dir)
    context["artifact_dir"] = str(promotion_dir)
    ops_record = _tail_promotion_log(args.strategy_id)
    if ops_record:
        context["ops_record"] = ops_record
    package_archive: Optional[Path] = None
    if promotion_dir and ops_record:
        package_path = ops_record.get("package")
        if package_path:
            package_archive = _archive_package(Path(package_path), promotion_dir)
            if package_archive:
                context["package_archive"] = str(package_archive)

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
        "artifact_dir": context.get("artifact_dir"),
    }
    _append_promotion_log(log_payload)
    print(f"[demo-promote] Registro actualizado en {PROMOTION_LOG}")

    control_ok = False
    control_detail: Optional[str] = None
    if args.control_api:
        try:
            control_ok, control_detail = _trigger_control(args)
            print(f"[demo-promote] Control API ejecutado: {control_detail}")
        except Exception as exc:
            print(f"[demo-promote] Control API falló: {exc}", file=sys.stderr)
            return 3
    context["control_executed"] = control_ok
    context["control_detail"] = control_detail

    smoke_result: Optional[Dict[str, Any]] = None
    smoke_stdout = ""
    smoke_stderr = ""
    if args.smoke_cmd:
        print(f"[demo-promote] Ejecutando smoke cmd: {args.smoke_cmd}")
        proc = subprocess.run(args.smoke_cmd, shell=True, capture_output=True, text=True, env=os.environ.copy())
        smoke_result = {
            "cmd": args.smoke_cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
        smoke_stdout, smoke_stderr = proc.stdout, proc.stderr
    elif args.auto_smoke:
        auto_api_base = args.smoke_api_base or args.api_base
        auto_panel_token = args.smoke_panel_token or args.panel_token
        auto_control_user = args.smoke_control_user or args.control_user
        auto_control_password = args.smoke_control_password or args.control_password
        print("[demo-promote] Ejecutando smoke interno scripts/tests/e2e_smoke.py")
        rc, out, err = _run_internal_smoke(auto_api_base, auto_panel_token, auto_control_user, auto_control_password)
        smoke_result = {
            "cmd": "internal_e2e_smoke",
            "returncode": rc,
            "stdout": out,
            "stderr": err,
            "api_base": auto_api_base,
        }
        smoke_stdout, smoke_stderr = out, err
    if smoke_result:
        context["smoke"] = smoke_result
        if promotion_dir:
            (promotion_dir / "smoke.log").write_text(
                smoke_stdout + "\n--- stderr ---\n" + smoke_stderr,
                encoding="utf-8",
            )
        if smoke_result["returncode"] != 0 and not args.allow_smoke_fail:
            print("[demo-promote] Smoke test falló; abortando promoción.", file=sys.stderr)
            return smoke_result["returncode"] or 4

    if promotion_dir:
        if args.package_config:
            sources = [state_path]
            if CONFIG_FILE:
                sources.append(CONFIG_FILE)
            snap = _snapshot_config(promotion_dir, [src for src in sources if src])
            if snap:
                context["config_snapshot"] = str(snap)
        checklist = _render_checklist(
            args.strategy_id,
            context,
            smoke_cmd=args.smoke_cmd,
            notes=args.notes,
            qa_owner=args.qa_owner,
        )
        _write_json(promotion_dir / "metadata.json", context)
        (promotion_dir / "checklist.md").write_text(checklist, encoding="utf-8")
        print(f"[demo-promote] Artefactos almacenados en {promotion_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
