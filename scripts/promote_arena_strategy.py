#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARENA_DIR = ROOT / "bot" / "arena"
REGISTRY_PATH = ARENA_DIR / "registry.json"
PROMOTED_DIR = ARENA_DIR / "promoted"


def load_registry(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"Registro no encontrado: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main(strategy_id: str, dest: Path | None = None) -> None:
    registry = load_registry(REGISTRY_PATH)
    target = next((entry for entry in registry if entry.get("id") == strategy_id), None)
    if not target:
        raise SystemExit(f"Estrategia {strategy_id} no encontrada en registry.json")

    dest_dir = dest or PROMOTED_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    outfile = dest_dir / f"{strategy_id}.json"
    outfile.write_text(json.dumps(target, indent=2), encoding="utf-8")
    print(f"Estrategia {strategy_id} exportada a {outfile}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Promueve una estrategia de la arena para modo real")
    parser.add_argument("strategy_id", help="ID en registry.json (ej. scalp_42)")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directorio destino (default bot/arena/promoted)")
    args = parser.parse_args()
    main(args.strategy_id, args.output_dir)
