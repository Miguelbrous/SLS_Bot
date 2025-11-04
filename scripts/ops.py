#!/usr/bin/env python3
"""CLI unificado para operar el stack SLS_Bot."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import os
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
DEPLOY_BOOTSTRAP = ROOT / "scripts" / "deploy" / "bootstrap.sh"
MONITOR_GUARD = ROOT / "scripts" / "tools" / "monitor_guard.py"
DEFAULT_SYSTEMD_SERVICES = [
    "sls-api.service",
    "sls-bot.service",
    "sls-cerebro.service",
    "sls-panel.service",
]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.arena.service import ArenaService


def _run(
    cmd: List[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    env: dict | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd or ROOT, check=check, env=env)


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
    cmd = [
        _python_exec(),
        str(ARENA_PROMOTE),
        args.strategy_id,
        "--min-trades",
        str(args.min_trades),
        "--min-sharpe",
        str(args.min_sharpe),
        "--max-drawdown",
        str(args.max_drawdown),
    ]
    if args.output_dir:
        cmd.extend(["--output-dir", args.output_dir])
    if args.force:
        cmd.append("--force")
    _run(cmd)


def cmd_arena_ranking(args: argparse.Namespace) -> None:
    data = json.loads(ARENA_RANKING.read_text(encoding="utf-8")) if ARENA_RANKING.exists() else []
    limit = args.limit
    for idx, row in enumerate(data[:limit], start=1):
        print(f"{idx:02d}. {row.get('name')} [{row.get('category')}] score={row.get('score'):.3f} balance={row.get('balance')} goal={row.get('goal')}")


def cmd_arena_state(args: argparse.Namespace) -> None:
    data = json.loads(ARENA_STATE.read_text(encoding="utf-8")) if ARENA_STATE.exists() else {}
    print(json.dumps(data, indent=2))


def cmd_arena_note_add(args: argparse.Namespace) -> None:
    from bot.arena.storage import ArenaStorage

    storage = ArenaStorage()
    record = storage.add_note(args.strategy_id, args.message, args.author)
    print(json.dumps(record, ensure_ascii=False, indent=2))


def cmd_arena_note_list(args: argparse.Namespace) -> None:
    from bot.arena.storage import ArenaStorage

    storage = ArenaStorage()
    notes = storage.notes_for(args.strategy_id, limit=args.limit)
    print(json.dumps(notes, ensure_ascii=False, indent=2))


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


def cmd_cerebro_train(args: argparse.Namespace) -> None:
    cmd = [_python_exec(), "-m", "bot.cerebro.train"]
    if args.mode:
        cmd.extend(["--mode", args.mode])
    if args.dataset:
        cmd.extend(["--dataset", args.dataset])
    if args.output_dir:
        cmd.extend(["--output-dir", args.output_dir])
    cmd.extend([
        "--epochs",
        str(args.epochs),
        "--lr",
        str(args.lr),
        "--train-ratio",
        str(args.train_ratio),
        "--min-auc",
        str(args.min_auc),
        "--min-win-rate",
        str(args.min_win_rate),
        "--seed",
        str(args.seed),
    ])
    if args.dry_run:
        cmd.append("--dry-run")
    if args.no_promote:
        cmd.append("--no-promote")
    _run(cmd)


def cmd_deploy_bootstrap(args: argparse.Namespace) -> None:
    env = os.environ.copy()
    env["APP_ROOT"] = args.app_root or env.get("APP_ROOT") or str(ROOT)
    env["SVC_USER"] = args.svc_user or env.get("SVC_USER") or os.environ.get("USER", "sls")
    if args.install_systemd or env.get("INSTALL_SYSTEMD"):
        env["INSTALL_SYSTEMD"] = "1"
    cmd = ["bash", str(DEPLOY_BOOTSTRAP)]
    _run(cmd, env=env)


def cmd_deploy_rollout(args: argparse.Namespace) -> None:
    services = args.services or DEFAULT_SYSTEMD_SERVICES
    if args.daemon_reload:
        _run(["systemctl", "daemon-reload"])
    for service in services:
        action = "restart" if args.restart else "reload"
        _run(["systemctl", action, service])
    if args.status:
        for service in services:
            _run(["systemctl", "status", service], check=False)


def cmd_monitor_check(args: argparse.Namespace) -> None:
    cmd = [
        _python_exec(),
        str(MONITOR_GUARD),
        "--api-base",
        args.api_base,
        "--max-arena-lag",
        str(args.max_arena_lag),
        "--max-drawdown",
        str(args.max_drawdown),
        "--max-ticks-since-win",
        str(args.max_ticks_since_win),
    ]
    if args.panel_token:
        cmd.extend(["--panel-token", args.panel_token])
    if args.slack_webhook:
        cmd.extend(["--slack-webhook", args.slack_webhook])
    if args.telegram_token:
        if not args.telegram_chat_id:
            raise SystemExit("Debes especificar --telegram-chat-id junto al token.")
        cmd.extend(
            ["--telegram-token", args.telegram_token, "--telegram-chat-id", args.telegram_chat_id]
        )
    if args.dry_run:
        cmd.append("--dry-run")
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

    deploy = sub.add_parser("deploy", help="Automatiza bootstrap/rollouts de servicios")
    deploy_sub = deploy.add_subparsers(dest="deploy_cmd", required=True)

    deploy_bootstrap = deploy_sub.add_parser("bootstrap", help="Ejecuta scripts/deploy/bootstrap.sh")
    deploy_bootstrap.add_argument("--app-root", help="Sobrescribe APP_ROOT al ejecutar el script")
    deploy_bootstrap.add_argument("--svc-user", help="Usuario del servicio (SVC_USER)")
    deploy_bootstrap.add_argument("--install-systemd", action="store_true", help="Copia unit files systemd")
    deploy_bootstrap.set_defaults(func=cmd_deploy_bootstrap)

    deploy_rollout = deploy_sub.add_parser("rollout", help="Reinicia servicios systemd")
    deploy_rollout.add_argument(
        "--services",
        nargs="+",
        help="Listado de unidades systemd a operar (default sls-*)",
    )
    deploy_rollout.add_argument("--daemon-reload", action="store_true", help="systemctl daemon-reload antes")
    deploy_rollout.add_argument("--status", action="store_true", help="Muestra systemctl status tras reiniciar")
    deploy_rollout.add_argument("--restart", action="store_true", help="Usa restart en lugar de reload")
    deploy_rollout.set_defaults(func=cmd_deploy_rollout)

    arena = sub.add_parser("arena", help="Operaciones relacionadas a la arena")
    arena_sub = arena.add_subparsers(dest="arena_cmd", required=True)

    arena_tick = arena_sub.add_parser("tick", help="Ejecuta un ciclo de la arena")
    arena_tick.set_defaults(func=cmd_arena_tick)

    arena_run = arena_sub.add_parser("run", help="Corre la arena en loop (bloqueante)")
    arena_run.add_argument("--interval", type=int, default=300, help="Segundos entre ticks (>=30)")
    arena_run.set_defaults(func=cmd_arena_run)

    arena_promote = arena_sub.add_parser("promote", help="Exporta una estrategia ganadora")
    arena_promote.add_argument("strategy_id", help="ID presente en registry.json")
    arena_promote.add_argument("--output-dir", help="Directorio destino opcional")
    arena_promote.add_argument("--min-trades", type=int, default=50, help="Trades mínimos requeridos")
    arena_promote.add_argument("--min-sharpe", type=float, default=0.2, help="Sharpe mínimo")
    arena_promote.add_argument("--max-drawdown", type=float, default=35.0, help="Max drawdown permitido (%)")
    arena_promote.add_argument("--force", action="store_true", help="Ignorar validaciones")
    arena_promote.set_defaults(func=cmd_arena_promote)

    arena_rank = arena_sub.add_parser("ranking", help="Muestra el top actual")
    arena_rank.add_argument("--limit", type=int, default=10)
    arena_rank.set_defaults(func=cmd_arena_ranking)

    arena_state = arena_sub.add_parser("state", help="Muestra el estado actual de la copa")
    arena_state.set_defaults(func=cmd_arena_state)

    arena_notes = arena_sub.add_parser("notes", help="Gestiona notas de estrategias")
    arena_notes_sub = arena_notes.add_subparsers(dest="notes_cmd", required=True)

    arena_note_add = arena_notes_sub.add_parser("add", help="Agrega una nota")
    arena_note_add.add_argument("strategy_id")
    arena_note_add.add_argument("--message", required=True, help="Contenido de la nota")
    arena_note_add.add_argument("--author", default="ops", help="Autor opcional")
    arena_note_add.set_defaults(func=cmd_arena_note_add)

    arena_note_list = arena_notes_sub.add_parser("list", help="Lista notas recientes")
    arena_note_list.add_argument("strategy_id")
    arena_note_list.add_argument("--limit", type=int, default=10)
    arena_note_list.set_defaults(func=cmd_arena_note_list)

    cerebro = sub.add_parser("cerebro", help="Flujos relacionados con el Cerebro IA")
    cerebro_sub = cerebro.add_subparsers(dest="cerebro_cmd", required=True)

    cerebro_dataset = cerebro_sub.add_parser("dataset", help="Genera un dataset sintético")
    cerebro_dataset.add_argument("--mode", default="test", help="Modo objetivo (test, real, etc.)")
    cerebro_dataset.add_argument("--rows", type=int, default=200, help="Número de filas a generar (>=50)")
    cerebro_dataset.add_argument("--bias", type=float, default=0.0, help="Sesgo adicional para pnl")
    cerebro_dataset.add_argument("--overwrite", action="store_true", help="Sobrescribir dataset existente")
    cerebro_dataset.set_defaults(func=cmd_cerebro_dataset)

    cerebro_train = cerebro_sub.add_parser("train", help="Entrena el modelo ligero del Cerebro")
    cerebro_train.add_argument("--mode", help="Modo objetivo (test, real, etc.)")
    cerebro_train.add_argument("--dataset", help="Ruta al dataset JSONL (opcional)")
    cerebro_train.add_argument("--output-dir", help="Directorio de artefactos (opcional)")
    cerebro_train.add_argument("--epochs", type=int, default=400)
    cerebro_train.add_argument("--lr", type=float, default=0.05)
    cerebro_train.add_argument("--train-ratio", type=float, default=0.8)
    cerebro_train.add_argument("--min-auc", type=float, default=0.52)
    cerebro_train.add_argument("--min-win-rate", type=float, default=0.52)
    cerebro_train.add_argument("--seed", type=int, default=42)
    cerebro_train.add_argument("--dry-run", action="store_true", help="Solo imprime métricas")
    cerebro_train.add_argument("--no-promote", action="store_true", help="No promueve automáticamente")
    cerebro_train.set_defaults(func=cmd_cerebro_train)

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

    monitor = sub.add_parser("monitor", help="Monitoreo activo de /metrics y /arena/state")
    monitor_sub = monitor.add_subparsers(dest="monitor_cmd", required=True)

    monitor_check = monitor_sub.add_parser("check", help="Valida métricas y envía alertas (Slack/Telegram)")
    monitor_check.add_argument("--api-base", default="http://127.0.0.1:8880", help="Base URL de la API")
    monitor_check.add_argument("--panel-token", help="Token del panel para acceder a /arena/state")
    monitor_check.add_argument("--max-arena-lag", type=int, default=600, help="Umbral de atraso para ticks (s)")
    monitor_check.add_argument("--max-drawdown", type=float, default=30.0, help="Drawdown (%) máximo permitido")
    monitor_check.add_argument(
        "--max-ticks-since-win",
        type=int,
        default=20,
        help="Ticks sin promover campeones antes de alertar",
    )
    monitor_check.add_argument("--slack-webhook", help="Webhook Slack opcional")
    monitor_check.add_argument("--telegram-token", help="Token del bot de Telegram")
    monitor_check.add_argument("--telegram-chat-id", help="Chat ID de Telegram")
    monitor_check.add_argument("--dry-run", action="store_true", help="No envía alertas, solo imprime")
    monitor_check.set_defaults(func=cmd_monitor_check)

    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
