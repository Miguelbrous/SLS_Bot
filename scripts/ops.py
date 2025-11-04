#!/usr/bin/env python3
"""CLI unificado para operar el stack SLS_Bot."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT / "venv"
SITE_PACKAGES = VENV_DIR / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
if SITE_PACKAGES.exists() and str(SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(SITE_PACKAGES))
MANAGE_SH = ROOT / "scripts" / "manage.sh"
ARENA_TICK = ROOT / "scripts" / "run_arena_tick.sh"
ARENA_PROMOTE = ROOT / "scripts" / "promote_arena_strategy.py"
ARENA_RANKING = ROOT / "bot" / "arena" / "ranking_latest.json"
ARENA_STATE = ROOT / "bot" / "arena" / "cup_state.json"
HEALTH_SCRIPT = ROOT / "scripts" / "tools" / "healthcheck.py"
INFRA_CHECK = ROOT / "scripts" / "tools" / "infra_check.py"
GENERATE_DATASET = ROOT / "scripts" / "tools" / "generate_cerebro_dataset.py"
PROMOTE_MODEL = ROOT / "scripts" / "tools" / "promote_best_cerebro_model.py"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.arena.service import ArenaService


def _run(cmd: List[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd or ROOT, check=check)


def _python_exec() -> str:
    candidate = VENV_DIR / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return sys.executable or "python3"


def cmd_up(args: argparse.Namespace) -> None:
    _run([str(MANAGE_SH), "encender-todo"])


def cmd_down(args: argparse.Namespace) -> None:
    _run([str(MANAGE_SH), "apagar-todo"])


def cmd_status(args: argparse.Namespace) -> None:
    _run([str(MANAGE_SH), "estado"])


def cmd_logs(args: argparse.Namespace) -> None:
    target = args.service
    _run([str(MANAGE_SH), "tail", target], check=not args.no_follow)


def cmd_health(args: argparse.Namespace) -> None:
    extra = []
    if args.panel_token:
        extra.extend(["--panel-token", args.panel_token])
    if args.control_user:
        extra.extend(["--control-user", args.control_user])
    if args.control_password:
        extra.extend(["--control-password", args.control_password])
    _run([_python_exec(), str(HEALTH_SCRIPT), *extra])


def cmd_qa(args: argparse.Namespace) -> None:
    print("[qa] Ejecutando pytest…")
    _run([_python_exec(), "-m", "pytest"])
    if not args.skip_panel:
        print("[qa] Ejecutando npm run lint…")
        _run(["npm", "run", "lint"], cwd=ROOT / "panel")
    print("[qa] QA completado")


def cmd_arena_tick(args: argparse.Namespace) -> None:
    _run([str(ARENA_TICK)])


def cmd_arena_run(args: argparse.Namespace) -> None:
    interval = max(30, args.interval)
    service = ArenaService(interval_seconds=interval)
    try:
        print(f"[arena] Loop iniciado (cada {interval}s). Ctrl+C para detener.")
        service.run_forever()
    except KeyboardInterrupt:
        print("[arena] Detenido manualmente.")
    finally:
        service.stop()


def cmd_arena_promote(args: argparse.Namespace) -> None:
    _run([_python_exec(), str(ARENA_PROMOTE), args.strategy_id])


def cmd_arena_ranking(args: argparse.Namespace) -> None:
    data = json.loads(ARENA_RANKING.read_text(encoding="utf-8")) if ARENA_RANKING.exists() else []
    limit = args.limit
    for idx, row in enumerate(data[:limit], start=1):
        print(f"{idx:02d}. {row.get('name')} [{row.get('category')}] score={row.get('score'):.3f} balance={row.get('balance')} goal={row.get('goal')}")


def cmd_arena_state(args: argparse.Namespace) -> None:
    data = json.loads(ARENA_STATE.read_text(encoding="utf-8")) if ARENA_STATE.exists() else {}
    print(json.dumps(data, indent=2))


def cmd_infra(args: argparse.Namespace) -> None:
    extra: List[str] = []
    if args.env_file:
        extra.extend(["--env-file", args.env_file])
    if args.ensure_dirs:
        extra.append("--ensure-dirs")
    _run([_python_exec(), str(INFRA_CHECK), *extra])


def cmd_cerebro_dataset(args: argparse.Namespace) -> None:
    cmd = [
        _python_exec(),
        str(GENERATE_DATASET),
        "--mode",
        args.mode,
        "--rows",
        str(args.rows),
    ]
    if args.bias is not None:
        cmd.extend(["--bias", str(args.bias)])
    if args.overwrite:
        cmd.append("--overwrite")
    _run(cmd)


def cmd_cerebro_promote(args: argparse.Namespace) -> None:
    cmd = [
        _python_exec(),
        str(PROMOTE_MODEL),
        "--mode",
        args.mode,
        "--metric",
        args.metric,
    ]
    if args.min_value is not None:
        cmd.extend(["--min-value", str(args.min_value)])
    _run(cmd)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CLI operativo para SLS_Bot")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub_up = sub.add_parser("up", help="Enciende API, bot, Cerebro y estrategia")
    sub_up.set_defaults(func=cmd_up)

    sub_down = sub.add_parser("down", help="Apaga todos los servicios")
    sub_down.set_defaults(func=cmd_down)

    sub_status = sub.add_parser("status", help="Estado de los servicios")
    sub_status.set_defaults(func=cmd_status)

    sub_logs = sub.add_parser("logs", help="Sigue logs de un servicio")
    sub_logs.add_argument("service", choices=["api", "bot", "cerebro", "estrategia"], help="Servicio a observar")
    sub_logs.add_argument("--no-follow", action="store_true", help="Mostrar únicamente los últimos registros (sin tail -f)")
    sub_logs.set_defaults(func=cmd_logs)

    sub_health = sub.add_parser("health", help="Ejecuta scripts/tools/healthcheck.py")
    sub_health.add_argument("--panel-token", dest="panel_token")
    sub_health.add_argument("--control-user", dest="control_user")
    sub_health.add_argument("--control-password", dest="control_password")
    sub_health.set_defaults(func=cmd_health)

    sub_qa = sub.add_parser("qa", help="Ejecuta suite rápida de validaciones")
    sub_qa.add_argument("--skip-panel", action="store_true", help="Omitir npm run lint para el panel")
    sub_qa.set_defaults(func=cmd_qa)

    sub_infra = sub.add_parser("infra", help="Valida config/env aprovechando infra_check.py")
    sub_infra.add_argument("--env-file", dest="env_file", help="Ruta a .env opcional")
    sub_infra.add_argument("--ensure-dirs", action="store_true", help="Crear directorios faltantes")
    sub_infra.set_defaults(func=cmd_infra)

    arena = sub.add_parser("arena", help="Operaciones relacionadas a la arena")
    arena_sub = arena.add_subparsers(dest="arena_cmd", required=True)

    arena_tick = arena_sub.add_parser("tick", help="Ejecuta un ciclo de la arena")
    arena_tick.set_defaults(func=cmd_arena_tick)

    arena_run = arena_sub.add_parser("run", help="Corre la arena en loop (bloqueante)")
    arena_run.add_argument("--interval", type=int, default=300, help="Segundos entre ticks (>=30)")
    arena_run.set_defaults(func=cmd_arena_run)

    arena_promote = arena_sub.add_parser("promote", help="Exporta una estrategia ganadora")
    arena_promote.add_argument("strategy_id", help="ID presente en registry.json")
    arena_promote.set_defaults(func=cmd_arena_promote)

    arena_rank = arena_sub.add_parser("ranking", help="Muestra el top actual")
    arena_rank.add_argument("--limit", type=int, default=10)
    arena_rank.set_defaults(func=cmd_arena_ranking)

    arena_state = arena_sub.add_parser("state", help="Muestra el estado actual de la copa")
    arena_state.set_defaults(func=cmd_arena_state)

    cerebro = sub.add_parser("cerebro", help="Flujos relacionados con el Cerebro IA")
    cerebro_sub = cerebro.add_subparsers(dest="cerebro_cmd", required=True)

    cerebro_dataset = cerebro_sub.add_parser("dataset", help="Genera un dataset sintético")
    cerebro_dataset.add_argument("--mode", default="test", help="Modo objetivo (test, real, etc.)")
    cerebro_dataset.add_argument("--rows", type=int, default=200, help="Número de filas a generar (>=50)")
    cerebro_dataset.add_argument("--bias", type=float, default=0.0, help="Sesgo adicional para pnl")
    cerebro_dataset.add_argument("--overwrite", action="store_true", help="Sobrescribir dataset existente")
    cerebro_dataset.set_defaults(func=cmd_cerebro_dataset)

    cerebro_promote = cerebro_sub.add_parser("promote", help="Promueve el mejor modelo registrado")
    cerebro_promote.add_argument("--mode", default="test", help="Modo objetivo (test, real, etc.)")
    cerebro_promote.add_argument("--metric", default="auc", help="Métrica a optimizar en el registry")
    cerebro_promote.add_argument(
        "--min-value",
        type=float,
        default=None,
        help="Mínimo requerido para la métrica seleccionada",
    )
    cerebro_promote.set_defaults(func=cmd_cerebro_promote)

    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
