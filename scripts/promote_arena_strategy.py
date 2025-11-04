#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
ARENA_DIR = ROOT / "bot" / "arena"
REGISTRY_PATH = ARENA_DIR / "registry.json"
PROMOTED_DIR = ARENA_DIR / "promoted"

if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

from bot.arena.storage import ArenaStorage  # noqa: E402


def load_registry(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"Registro no encontrado: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _create_package_dir(base: Path, strategy_id: str) -> Path:
    pkg_dir = base / strategy_id
    pkg_dir.mkdir(parents=True, exist_ok=True)
    return pkg_dir


def _render_summary(profile: dict, ledger: list[dict]) -> str:
    stats = profile.get("stats") or {}
    latest = ledger[-1] if ledger else {}
    now = datetime.utcnow().isoformat()
    lines = [
        f"# {profile.get('name')} ({profile.get('id')})",
        "",
        f"- Categoría: **{profile.get('category')}**",
        f"- Modo actual: **{profile.get('mode')}** (engine: {profile.get('engine')})",
        f"- Balance actual: {latest.get('balance_after', stats.get('balance'))}",
        f"- Meta vigente: {stats.get('goal')} · Wins: {stats.get('wins', 0)} · Losses: {stats.get('losses', 0)}",
        f"- Última actualización arena: {latest.get('ts', 'N/A')}",
        "",
        "Incluye `profile.json` y `ledger_tail.json` con los últimos movimientos registrados.",
        f"Paquete generado {now} UTC.",
    ]
    return "\n".join(lines)


def main(strategy_id: str, dest: Path | None = None) -> None:
    registry = load_registry(REGISTRY_PATH)
    target = next((entry for entry in registry if entry.get("id") == strategy_id), None)
    if not target:
        raise SystemExit(f"Estrategia {strategy_id} no encontrada en registry.json")

    storage = ArenaStorage()
    ledger = storage.ledger_for(strategy_id, limit=100)

    dest_dir = dest or PROMOTED_DIR
    package_dir = _create_package_dir(dest_dir, strategy_id)
    (package_dir / "profile.json").write_text(json.dumps(target, indent=2), encoding="utf-8")
    (package_dir / "ledger_tail.json").write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    (package_dir / "SUMMARY.md").write_text(_render_summary(target, ledger), encoding="utf-8")
    print(f"Estrategia {strategy_id} exportada en {package_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Promueve una estrategia de la arena para modo real")
    parser.add_argument("strategy_id", help="ID en registry.json (ej. scalp_42)")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directorio destino (default bot/arena/promoted)")
    args = parser.parse_args()
    main(args.strategy_id, args.output_dir)
