from pathlib import Path
import os
import json
from typing import Optional

CFG_PATH_IN_USE: Optional[str] = None

def _strip_json_comments(s: str) -> str:
    """Elimina // y /* */ sin tocar contenido dentro de cadenas."""
    out = []
    i, n = 0, len(s)
    in_str = False
    in_line = False
    in_block = False
    while i < n:
        ch = s[i]
        nxt = s[i+1] if i+1 < n else ''
        if in_line:
            if ch == '\n':
                in_line = False
                out.append(ch)
            i += 1
            continue
        if in_block:
            if ch == '*' and nxt == '/':
                in_block = False
                i += 2
            else:
                i += 1
            continue
        if in_str:
            out.append(ch)
            if ch == '\\' and i+1 < n:
                out.append(s[i+1]); i += 2; continue
            if ch == '"':
                in_str = False
            i += 1
            continue
        # fuera de cadena
        if ch == '"':
            in_str = True
            out.append(ch); i += 1; continue
        if ch == '/' and nxt == '/':
            in_line = True; i += 2; continue
        if ch == '/' and nxt == '*':
            in_block = True; i += 2; continue
        out.append(ch); i += 1
    return ''.join(out)

def _json_load_permissive(p: Path) -> dict:
    s = p.read_text(encoding="utf-8")
    if s and s[0] == "\ufeff":  # BOM
        s = s[1:]
    s = _strip_json_comments(s)
    # eliminar comas finales antes de } o ]
    import re
    s = re.sub(r",\s*(?=[}\]])", "", s)
    return json.loads(s)

def load_config() -> dict:
    """
    Carga el config.json (por variable de entorno o rutas conocidas del proyecto).
    Acepta comentarios // y /* */ y comas finales.
    """
    global CFG_PATH_IN_USE

    env_path = os.getenv("SLSBOT_CONFIG")
    if env_path:
        p = Path(env_path)
        if p.exists():
            CFG_PATH_IN_USE = str(p)
            return _json_load_permissive(p)

    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "config" / "config.json",
        here.parents[1] / "config" / "config.json",
        Path.cwd().parent / "config" / "config.json",
        Path.cwd() / "config" / "config.json",
    ]
    for c in candidates:
        if c.exists():
            CFG_PATH_IN_USE = str(c)
            return _json_load_permissive(c)

    raise FileNotFoundError(
        "No se encontró config.json. Define SLSBOT_CONFIG o coloca el archivo en /config/config.json."
    )
