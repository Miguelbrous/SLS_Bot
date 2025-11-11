#!/usr/bin/env python3
"""
Verifica configuraciones sensibles (.env + config) para el frente F4.
Comprueba que existan los secretos mínimos y que las rutas críticas sean válidas.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

DEFAULT_ENV = ".env"
DEFAULT_CONFIG = "config/config.json"
TOKEN_RE = re.compile(r"^[^@]+@\d{4}-\d{2}-\d{2}$")
DEFAULT_CONTROL_USER = "panel_admin"
DEFAULT_CONTROL_PASSWORD = "cambia_est0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Security checklist for SLS Bot.")
    parser.add_argument("--env-file", default=DEFAULT_ENV, help="Ruta al archivo .env (por defecto .env).")
    parser.add_argument(
        "--config-json", default=DEFAULT_CONFIG, help="Ruta al config JSON con perfiles (por defecto config/config.json)."
    )
    return parser.parse_args()


def load_env(path: Path) -> Dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo .env en {path}")
    env: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def load_config(path: Path) -> Dict:
    if not path.exists():
        raise FileNotFoundError(f"No existe config JSON en {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def check_env(env: Dict[str, str]) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    audit_log = env.get("AUDIT_LOG")
    if not audit_log:
        errors.append("AUDIT_LOG no definido en .env")
    else:
        audit_path = Path(audit_log).expanduser()
        parent = audit_path.parent
        if not parent.exists():
            warnings.append(f"El directorio {parent} no existe (AUDIT_LOG apuntará a ruta inexistente)")

    for key in ("CONTROL_USER", "CONTROL_PASSWORD"):
        if not env.get(key):
            errors.append(f"{key} no está definido en .env")
    if env.get("CONTROL_USER") == DEFAULT_CONTROL_USER:
        warnings.append("CONTROL_USER usa el valor por defecto (panel_admin)")
    if env.get("CONTROL_PASSWORD") == DEFAULT_CONTROL_PASSWORD:
        warnings.append("CONTROL_PASSWORD usa el valor por defecto (cambia_est0)")

    rl_req = env.get("RATE_LIMIT_REQUESTS")
    rl_win = env.get("RATE_LIMIT_WINDOW")
    if not rl_req or not rl_win:
        warnings.append("RATE_LIMIT_REQUESTS/WINDOW no están configurados (se usará rate limit por defecto)")
    else:
        for key, value in (("RATE_LIMIT_REQUESTS", rl_req), ("RATE_LIMIT_WINDOW", rl_win)):
            try:
                if int(value) <= 0:
                    warnings.append(f"{key} debe ser un entero positivo (valor actual: {value})")
            except ValueError:
                errors.append(f"{key} debe ser numérico (valor actual: {value})")

    tokens_raw = env.get("PANEL_API_TOKENS", "")
    tokens = [token.strip() for token in tokens_raw.split(",") if token.strip()]
    if not tokens:
        errors.append("PANEL_API_TOKENS vacío: el panel no podrá autenticarse")
    else:
        for token in tokens:
            if "@" not in token:
                warnings.append(f"Token '{token}' no tiene fecha de expiración (formato token@YYYY-MM-DD)")
            elif not TOKEN_RE.match(token):
                warnings.append(f"Token '{token}' no cumple formato token@YYYY-MM-DD")

    if env.get("SLSBOT_CONFIG"):
        cfg_path = Path(env["SLSBOT_CONFIG"]).expanduser()
        if not cfg_path.exists():
            errors.append(f"SLSBOT_CONFIG apunta a {cfg_path} pero el archivo no existe")
    else:
        warnings.append("SLSBOT_CONFIG no definido en .env (se usará config/config.json)")

    return errors, warnings


def check_config(cfg: Dict) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    shared_paths = ((cfg or {}).get("shared") or {}).get("paths") or {}
    for key in ("excel_dir", "logs_dir", "models_dir"):
        value = shared_paths.get(key)
        if not value:
            warnings.append(f"shared.paths.{key} no está definido en config/config.json")
    modes = (cfg or {}).get("modes") or {}
    if "real" not in modes or "test" not in modes:
        errors.append("config/config.json debe contener los perfiles 'test' y 'real'")
    return errors, warnings


def main() -> int:
    args = parse_args()
    env = load_env(Path(args.env_file))
    cfg = load_config(Path(args.config_json))
    env_errors, env_warnings = check_env(env)
    cfg_errors, cfg_warnings = check_config(cfg)

    all_errors = env_errors + cfg_errors
    all_warnings = env_warnings + cfg_warnings

    if all_errors:
        print("❌ Problemas críticos:")
        for item in all_errors:
            print(f"  - {item}")
    if all_warnings:
        print("⚠️ Advertencias:")
        for item in all_warnings:
            print(f"  - {item}")
    if not all_errors and not all_warnings:
        print("✅ Seguridad básica OK (.env + config)")
        return 0
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
