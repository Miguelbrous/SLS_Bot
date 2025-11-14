from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import StrategyProfile, StrategyStats
from .storage import ArenaStorage, DB_PATH
from .validator import validate_strategy, ValidationReport

ARENA_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = ARENA_DIR / "registry.json"
PROMOTED_DIR = ARENA_DIR / "promoted"


def _load_registry(path: Path = REGISTRY_PATH) -> dict[str, dict]:
    if not path.exists():
        raise FileNotFoundError(f"Registry not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return {entry["id"]: entry for entry in data}


def _render_summary(profile: dict, ledger: list[dict]) -> str:
    stats = profile.get("stats") or {}
    latest = ledger[-1] if ledger else {}
    now = datetime.utcnow().isoformat()
    lines = [
        f"# {profile.get('name')} ({profile.get('id')})",
        "",
        f"- Categoría: **{profile.get('category')}**",
        f"- Modo: **{profile.get('mode')}** · Engine: {profile.get('engine')}",
        f"- Balance actual: {latest.get('balance_after', stats.get('balance'))}",
        f"- Meta vigente: {stats.get('goal')} · Wins/Losses: {stats.get('wins', 0)}/{stats.get('losses', 0)}",
        f"- Trades totales: {stats.get('trades', stats.get('wins', 0) + stats.get('losses', 0))}",
        f"- Sharpe: {stats.get('sharpe_ratio', 0.0)} · Max DD: {stats.get('max_drawdown_pct', stats.get('drawdown_pct', 0.0))}%",
        f"- Último registro: {latest.get('ts', 'N/A')}",
        "",
        "Incluye `profile.json` y `ledger_tail.json` con los movimientos recientes.",
        f"Paquete generado {now} UTC.",
    ]
    return "\n".join(lines)


def _profile_from_dict(data: dict) -> StrategyProfile:
    stats_raw: dict[str, Any] | None = data.get("stats")
    stats = StrategyStats(**stats_raw) if stats_raw else None
    return StrategyProfile(
        id=data["id"],
        name=data.get("name", data["id"]),
        category=data.get("category", "scalp"),
        timeframe=data.get("timeframe", "1m"),
        indicators=data.get("indicators", []),
        mode=data.get("mode", "draft"),
        engine=data.get("engine", "sim"),
        stats=stats,
        notes=data.get("notes"),
    )


def export_strategy(
    strategy_id: str,
    *,
    dest_dir: Path | None = None,
    db_path: Path | None = None,
    min_trades: int = 50,
    min_sharpe: float = 0.2,
    max_drawdown: float = 35.0,
    force: bool = False,
) -> Path:
    registry = _load_registry()
    profile_dict = registry.get(strategy_id)
    if not profile_dict:
        raise ValueError(f"Estrategia {strategy_id} no existe en registry.json")
    profile = _profile_from_dict(profile_dict)

    storage = ArenaStorage(db_path or DB_PATH)
    ledger = storage.ledger_for(strategy_id, limit=100)
    report: ValidationReport | None = None
    if not force:
        report = validate_strategy(
            profile,
            min_trades=min_trades,
            min_sharpe=min_sharpe,
            max_drawdown=max_drawdown,
        )
        if not report.ok:
            raise ValueError("Validación de promoción fallida: " + "; ".join(report.reasons))
    else:
        report = validate_strategy(
            profile,
            min_trades=min_trades,
            min_sharpe=min_sharpe,
            max_drawdown=max_drawdown,
        )

    base_dir = dest_dir or PROMOTED_DIR
    pkg_dir = base_dir / strategy_id
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "profile.json").write_text(json.dumps(profile_dict, indent=2), encoding="utf-8")
    (pkg_dir / "ledger_tail.json").write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    (pkg_dir / "SUMMARY.md").write_text(_render_summary(profile_dict, ledger), encoding="utf-8")
    if report:
        (pkg_dir / "validation.json").write_text(
            json.dumps({"ok": report.ok, "reasons": report.reasons, "metrics": report.metrics}, indent=2),
            encoding="utf-8",
        )
    return pkg_dir
