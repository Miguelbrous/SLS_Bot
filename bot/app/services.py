import platform
import shutil
import subprocess
from typing import Tuple


def _systemctl_available() -> bool:
    return shutil.which("systemctl") is not None


def _is_linux() -> bool:
    return platform.system().lower() == "linux"


def service_status(service: str) -> Tuple[bool, str]:
    if not _is_linux() or not _systemctl_available():
        return False, "systemctl no disponible en esta máquina"
    try:
        out = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True,
            text=True,
            check=False,
        )
        active = out.stdout.strip() == "active"
        return active, out.stdout.strip() or out.stderr.strip()
    except Exception as e:
        return False, f"error: {e}"


def service_action(service: str, action: str) -> Tuple[bool, str]:
    if action == "status":
        return service_status(service)
    if not _is_linux() or not _systemctl_available():
        return False, "systemctl no disponible en esta máquina"
    if action not in {"start", "stop", "restart"}:
        return False, f"acción no válida: {action}"
    try:
        out = subprocess.run(
            ["systemctl", action, service],
            capture_output=True,
            text=True,
            check=False,
        )
        ok = out.returncode == 0
        detail = out.stdout.strip() or out.stderr.strip()
        return ok, detail or f"{service} {action}"
    except Exception as e:
        return False, f"error: {e}"
