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
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "bot"))

import sls_bot.config_loader as config_loader  # type: ignore  # noqa: E402
load_config = config_loader.load_config


def _read_env_file(path: Path | None) -> Dict[str, str]:
    """Lee un archivo .env plano (KEY=VALUE) ignorando comentarios."""
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


def _restore_mode(env_value: str | None) -> None:
    """Restablece la variable de modo que hubiera antes del chequeo."""
    if env_value is None:
        os.environ.pop("SLSBOT_MODE", None)
    else:
        os.environ["SLSBOT_MODE"] = env_value


def _resolve_path(raw: str | None) -> Path:
    """Convierte rutas relativas o con `~` a Paths absolutos dentro del repositorio."""
    if not raw:
        return REPO_ROOT
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve()
    return candidate


def _ensure_dir(path: Path, ensure: bool) -> Tuple[bool, bool]:
    """Devuelve (existe, creado) y opcionalmente crea el directorio si faltaba."""
    exists = path.exists()
    created = False
    if not exists and ensure:
        path.mkdir(parents=True, exist_ok=True)
        created = True
        exists = True
    return exists, created


def _token_is_valid(token: str) -> bool:
    """Valida tokens del panel con formato `token` o `token@YYYY-MM-DD`."""
    value = token.strip()
    if not value:
        return False
    if "@" not in value:
        return True
    prefix, suffix = value.split("@", 1)
    if not prefix:
        return False
    try:
        datetime.strptime(suffix, "%Y-%m-%d")
    except ValueError:
        return False
    return True


@dataclass
class ModeSummary:
    """Agrupa la información consolidada de un modo (test/real)."""

    name: str
    logs_dir: Path
    excel_dir: Path
    models_dir: Path
    metrics_dir: Path
    reports_dir: Path
    cerebro_enabled: bool
    bybit_base_url: str | None
    logs_dir_exists: bool
    excel_dir_exists: bool
    models_dir_exists: bool
    metrics_dir_exists: bool
    reports_dir_exists: bool
    created_dirs: List[str] = field(default_factory=list)

    def to_payload(self) -> Dict[str, object]:
        """Transforma el dataclass en un diccionario serializable."""
        payload = asdict(self)
        payload["logs_dir"] = str(self.logs_dir)
        payload["excel_dir"] = str(self.excel_dir)
        payload["models_dir"] = str(self.models_dir)
        payload["metrics_dir"] = str(self.metrics_dir)
        payload["reports_dir"] = str(self.reports_dir)
        return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Chequea config, variables y rutas necesarias.")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Ruta opcional a un archivo .env para validar.",
    )
    parser.add_argument(
        "--ensure-dirs",
        action="store_true",
        help="Crea directorios de logs/excel/modelos que falten para cada modo.",
    )
    args = parser.parse_args()

    original_mode = os.getenv("SLSBOT_MODE")

    cfg = load_config()
    env_data = _read_env_file(args.env_file)

    def _env_value(key: str) -> str | None:
        return os.getenv(key) or env_data.get(key)

    warnings: List[str] = []
    created_dirs: List[str] = []

    required_keys = ["BYBIT_API_KEY", "BYBIT_API_SECRET", "PANEL_API_TOKENS", "CONTROL_USER", "CONTROL_PASSWORD"]
    for key in required_keys:
        if not _env_value(key):
            target = args.env_file if args.env_file else "el entorno"
            warnings.append(f"Variable {key} no definida en {target}")

    panel_tokens_raw = _env_value("PANEL_API_TOKENS") or ""
    tokens = [tok.strip() for tok in panel_tokens_raw.split(",") if tok.strip()]
    invalid_tokens = [tok for tok in tokens if not _token_is_valid(tok)]
    if not tokens:
        warnings.append("Define PANEL_API_TOKENS con al menos un token válido (token o token@YYYY-MM-DD).")
    elif invalid_tokens:
        warnings.append(f"PANEL_API_TOKENS contiene formatos inválidos: {', '.join(invalid_tokens)}")

    if (cfg.get("auth") or {}).get("control_password") in {"cambia_esto", "cambia_est0"}:
        warnings.append("Actualiza auth.control_password en config.json (valor por defecto inseguro).")

    if (cfg.get("bybit") or {}).get("api_key") in {"TESTNET_API_KEY", "MAINNET_API_KEY"}:
        warnings.append("Reemplaza bybit.api_key/bybit.api_secret en config.json por tus credenciales reales.")

    available_modes = cfg.get("_available_modes") or (
        [cfg.get("_active_mode")] if cfg.get("_active_mode") else []
    )
    mode_summaries: Dict[str, ModeSummary] = {}

    try:
        for mode in available_modes:
            os.environ["SLSBOT_MODE"] = mode
            mode_cfg = load_config()

            paths = mode_cfg.get("paths") or {}
            logs_dir = _resolve_path(paths.get("logs_dir") or "./logs")
            excel_dir = _resolve_path(paths.get("excel_dir") or "./excel")

            cere_cfg = mode_cfg.get("cerebro") or {}
            models_dir = _resolve_path(cere_cfg.get("models_dir") or f"./models/cerebro/{mode}")
            metrics_dir = logs_dir / "metrics"
            reports_dir = logs_dir / "reports"

            logs_exists, logs_created = _ensure_dir(logs_dir, args.ensure_dirs)
            excel_exists, excel_created = _ensure_dir(excel_dir, args.ensure_dirs)
            models_exists, models_created = _ensure_dir(models_dir, args.ensure_dirs)
            metrics_exists, metrics_created = _ensure_dir(metrics_dir, args.ensure_dirs)
            reports_exists, reports_created = _ensure_dir(reports_dir, args.ensure_dirs)

            created = []
            if logs_created:
                created.append(str(logs_dir))
            if excel_created:
                created.append(str(excel_dir))
            if models_created:
                created.append(str(models_dir))
            if metrics_created:
                created.append(str(metrics_dir))
            if reports_created:
                created.append(str(reports_dir))
            created_dirs.extend(created)

            mode_summaries[mode] = ModeSummary(
                name=mode,
                logs_dir=logs_dir,
                excel_dir=excel_dir,
                models_dir=models_dir,
                metrics_dir=metrics_dir,
                reports_dir=reports_dir,
                cerebro_enabled=bool(cere_cfg.get("enabled")),
                bybit_base_url=(mode_cfg.get("bybit") or {}).get("base_url"),
                logs_dir_exists=logs_exists,
                excel_dir_exists=excel_exists,
                models_dir_exists=models_exists,
                metrics_dir_exists=metrics_exists,
                reports_dir_exists=reports_exists,
                created_dirs=created,
            )
    finally:
        _restore_mode(original_mode)

    result = {
        "config_path": config_loader.CFG_PATH_IN_USE,
        "active_mode": cfg.get("_active_mode"),
        "available_modes": available_modes,
        "env_checked": args.env_file.name if args.env_file else None,
        "warnings": warnings,
        "directories_created": created_dirs,
        "modes": {name: summary.to_payload() for name, summary in mode_summaries.items()},
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
