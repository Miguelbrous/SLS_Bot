#!/usr/bin/env python3
"""
Acciones simples para operar el stack del SLS Bot sin conocer comandos avanzados.

Uso básico (en el VPS, dentro de la carpeta del proyecto):
  python3 scripts/manage_bot.py encender
  python3 scripts/manage_bot.py apagar
  python3 scripts/manage_bot.py reiniciar
  python3 scripts/manage_bot.py diagnostico

Opcional: pasar un .env concreto
  python3 scripts/manage_bot.py encender --env-file /ruta/.env
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
INFRA_CHECK = REPO_ROOT / "scripts" / "tools" / "infra_check.py"

# Servicios principales; si alguno no existe en el VPS se ignora con un aviso.
CORE_SERVICES: List[str] = ["sls-api", "sls-bot", "ai-bridge"]
EXTRA_SERVICES: List[str] = ["sls-cerebro", "sls-panel"]


def _systemctl_available() -> bool:
    return shutil.which("systemctl") is not None


def _run(cmd: List[str]) -> Tuple[int, str]:
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = (result.stdout or "").strip() or (result.stderr or "").strip()
    return result.returncode, output


def _service_exists(name: str) -> bool:
    code, out = _run(["systemctl", "status", name])
    if "could not be found" in out.lower() or "Loaded: not-found" in out:
        return False
    # return code 0 (active) o 3 (inactive/failed) indican que la unidad existe
    return code in {0, 1, 2, 3}


def _service_action(name: str, action: str) -> Tuple[bool, str]:
    code, out = _run(["systemctl", action, name])
    ok = code == 0
    return ok, out or f"{name} {action}"


def _service_status(name: str) -> Tuple[str, str]:
    code, out = _run(["systemctl", "is-active", name])
    if code == 0:
        return "activo", out
    if code == 3:
        return "inactivo", out or "inactive"
    return "error", out or "desconocido"


def _collect_diagnostics(name: str, lines: int = 15) -> Dict[str, str]:
    status, status_raw = _service_status(name)
    code, journal = _run(["journalctl", "-u", name, "-n", str(lines), "--no-pager"])
    if code != 0 and not journal:
        journal = "No hay registros recientes o el servicio no existe."
    return {
        "servicio": name,
        "estado": status,
        "detalle_estado": status_raw,
        "logs_recientes": journal,
    }


def _print_json(data: Dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _run_infra_check(env_file: Path | None) -> Dict[str, object] | None:
    if not INFRA_CHECK.exists():
        return None
    cmd = ["python3", str(INFRA_CHECK)]
    if env_file:
        cmd.extend(["--env-file", str(env_file)])
    code, out = _run(cmd)
    if code != 0:
        return {"status": "error", "detalle": out or "infra_check fallo"}
    try:
        return json.loads(out)
    except Exception:
        return {"status": "ok", "detalle": out}


def accion_encender(env_file: Path | None) -> None:
    resumen = {"pasos": [], "servicios": []}

    check = _run_infra_check(env_file)
    if check:
        resumen["pasos"].append({"nombre": "infra_check", "resultado": check})

    for service in CORE_SERVICES + EXTRA_SERVICES:
        if not _service_exists(service):
            resumen["servicios"].append(
                {"servicio": service, "resultado": "omitido", "detalle": "no instalado"}
            )
            continue
        ok, detail = _service_action(service, "start")
        estado, estado_raw = _service_status(service)
        resumen["servicios"].append(
            {
                "servicio": service,
                "resultado": "ok" if ok else "error",
                "detalle": detail,
                "estado": estado,
                "detalle_estado": estado_raw,
            }
        )

    _print_json(resumen)


def accion_apagar() -> None:
    resumen = {"servicios": []}
    for service in CORE_SERVICES + EXTRA_SERVICES:
        if not _service_exists(service):
            resumen["servicios"].append(
                {"servicio": service, "resultado": "omitido", "detalle": "no instalado"}
            )
            continue
        ok, detail = _service_action(service, "stop")
        estado, estado_raw = _service_status(service)
        resumen["servicios"].append(
            {
                "servicio": service,
                "resultado": "ok" if ok else "error",
                "detalle": detail,
                "estado": estado,
                "detalle_estado": estado_raw,
            }
        )
    _print_json(resumen)


def accion_reiniciar(env_file: Path | None) -> None:
    resumen = {"pasos": [], "servicios": []}

    check = _run_infra_check(env_file)
    if check:
        resumen["pasos"].append({"nombre": "infra_check", "resultado": check})

    for service in CORE_SERVICES + EXTRA_SERVICES:
        if not _service_exists(service):
            resumen["servicios"].append(
                {"servicio": service, "resultado": "omitido", "detalle": "no instalado"}
            )
            continue
        ok, detail = _service_action(service, "restart")
        diag = _collect_diagnostics(service)
        resumen["servicios"].append(
            {
                "servicio": service,
                "resultado": "ok" if ok else "error",
                "detalle": detail,
                "diagnostico": diag,
            }
        )

    _print_json(resumen)


def accion_diagnostico() -> None:
    resumen = {"servicios": []}
    for service in CORE_SERVICES + EXTRA_SERVICES:
        if not _service_exists(service):
            resumen["servicios"].append(
                {"servicio": service, "resultado": "omitido", "detalle": "no instalado"}
            )
            continue
        resumen["servicios"].append({"servicio": service, "diagnostico": _collect_diagnostics(service)})
    _print_json(resumen)


def main() -> None:
    if not _systemctl_available():
        print("systemctl no está disponible en este sistema. Ejecuta este script en el VPS Ubuntu donde vive el bot.", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Control simple del SLS Bot.")
    parser.add_argument(
        "accion",
        choices=["encender", "apagar", "reiniciar", "diagnostico"],
        help="Operación a ejecutar sobre los servicios.",
    )
    parser.add_argument(
        "--env-file",
        dest="env_file",
        type=Path,
        default=None,
        help="Ruta opcional a un archivo .env para validar antes de encender/reiniciar.",
    )
    args = parser.parse_args()

    if args.env_file and not args.env_file.exists():
        parser.error(f"El archivo {args.env_file} no existe.")

    if args.accion == "encender":
        accion_encender(args.env_file)
    elif args.accion == "apagar":
        accion_apagar()
    elif args.accion == "reiniciar":
        accion_reiniciar(args.env_file)
    elif args.accion == "diagnostico":
        accion_diagnostico()
    else:
        parser.error("Acción no soportada.")


if __name__ == "__main__":
    main()
