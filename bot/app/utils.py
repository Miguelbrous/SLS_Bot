from collections import deque
from pathlib import Path
from typing import List


def tail_lines(path: Path, limit: int) -> List[str]:
    """
    Devuelve las últimas `limit` líneas del archivo `path`.
    Si no existe, devuelve lista vacía sin romper.
    """
    try:
        if not path.exists() or not path.is_file():
            return []
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            dq = deque(f, maxlen=limit)
        return list(dq)
    except Exception:
        return []
