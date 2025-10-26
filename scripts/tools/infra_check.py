#!/usr/bin/env python
"""
Valida configuración básica y variables de entorno antes de levantar el bot.

Ejemplo:
    python scripts/tools/infra_check.py --env-file .env
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "bot"))

from sls_bot.config_loader import CFG_PATH_IN_USE, load_config  # type: ignore  # noqa: E402


def _read_env_file(path: Path | None) -> Dict[str, str]:
    if not path or not path.exists():
        return {}
    data: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Chequea config y variables necesarias.")
    parser.add_argument("--env-file", type=Path, default=None, help="Ruta opcional a un archivo .env para validar.")
    args = parser.parse_args()

    cfg = load_config()
    env_data = _read_env_file(args.env_file)

    def _env_value(key: str) -> str | None:
        return os.getenv(key) or env_data.get(key)

    required_keys = ["BYBIT_API_KEY", "BYBIT_API_SECRET", "PANEL_API_TOKENS", "CONTROL_USER", "CONTROL_PASSWORD"]
    warnings = []
    for key in required_keys:
        if not _env_value(key):
            warnings.append(f"Variable {key} no definida en entorno ni en {args.env_file}")
    bybit_cfg = cfg.get("bybit") or {}
    if "YOUR" in str(bybit_cfg.get("api_key", "")):
        warnings.append("Reemplaza bybit.api_key/api_secret por credenciales reales en config.json")
    logs_dir = Path(cfg.get("paths", {}).get("logs_dir") or (REPO_ROOT / "logs"))
    excel_dir = Path(cfg.get("paths", {}).get("excel_dir") or (REPO_ROOT / "excel"))

    result = {
        "config_path": CFG_PATH_IN_USE,
        "active_mode": cfg.get("_active_mode"),
        "available_modes": cfg.get("_available_modes"),
        "bybit_base_url": bybit_cfg.get("base_url"),
        "logs_dir": str(logs_dir),
        "logs_dir_exists": logs_dir.exists(),
        "excel_dir": str(excel_dir),
        "excel_dir_exists": excel_dir.exists(),
        "env_checked": args.env_file.name if args.env_file else None,
        "warnings": warnings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
