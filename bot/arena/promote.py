from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .storage import ArenaStorage, DB_PATH

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
        f"- Meta vigente: {stats.get('goal')} · Wins: {stats.get('wins', 0)} · Losses: {stats.get('losses', 0)}",
        f"- Último registro: {latest.get('ts', 'N/A')}",
        "",
        "Incluye `profile.json` y `ledger_tail.json` con los movimientos recientes.",
        f"Paquete generado {now} UTC.",
    ]
    return "\n".join(lines)


def export_strategy(strategy_id: str, *, dest_dir: Path | None = None, db_path: Path | None = None) -> Path:
    registry = _load_registry()
    profile = registry.get(strategy_id)
    if not profile:
        raise ValueError(f"Estrategia {strategy_id} no existe en registry.json")

    storage = ArenaStorage(db_path or DB_PATH)
    ledger = storage.ledger_for(strategy_id, limit=100)

    base_dir = dest_dir or PROMOTED_DIR
    pkg_dir = base_dir / strategy_id
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "profile.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
    (pkg_dir / "ledger_tail.json").write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    (pkg_dir / "SUMMARY.md").write_text(_render_summary(profile, ledger), encoding="utf-8")
    return pkg_dir
