#!/usr/bin/env python3
"""
Promueve el mejor modelo del Cerebro IA según una métrica dada.

Ejemplo:
    python scripts/tools/promote_best_cerebro_model.py --mode test --metric auc --min-value 0.6
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cerebro.versioning import ModelRegistry

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description="Promueve el mejor modelo registrado del Cerebro IA.")
    parser.add_argument("--mode", type=str, default="test", help="Modo objetivo (test, real, etc.).")
    parser.add_argument(
        "--metric",
        type=str,
        default="auc",
        help="Métrica a optimizar (usa la clave guardada en el registry: auc, win_rate, accuracy, ...).",
    )
    parser.add_argument(
        "--min-value",
        type=float,
        default=None,
        help="Valor mínimo requerido para promover (opcional).",
    )
    args = parser.parse_args()

    models_dir = ROOT / "models" / "cerebro" / args.mode
    registry = ModelRegistry(models_dir)
    best = registry.best(args.metric, args.min_value)
    if not best:
        print(json.dumps({"ok": False, "reason": "no_candidate", "metric": args.metric}, ensure_ascii=False))
        raise SystemExit(1)
    promoted = registry.promote(best.id)
    if not promoted:
        print(json.dumps({"ok": False, "reason": "promote_failed", "candidate": best.id}, ensure_ascii=False))
        raise SystemExit(2)
    payload = {
        "ok": True,
        "mode": args.mode,
        "metric": args.metric,
        "candidate": best.id,
        "metrics": best.metrics,
        "active_path": str(promoted.path),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
