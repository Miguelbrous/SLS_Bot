from pathlib import Path
import os
import json
from typing import Optional, Any, Dict

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


def _deep_merge(base: Any, override: Any) -> Any:
    if not isinstance(base, dict) or not isinstance(override, dict):
        return override
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _render_mode_tokens(data: Any, mode: str) -> Any:
    """Permite usar {mode} en cadenas de config."""
    if isinstance(data, str):
        return data.replace("{mode}", mode)
    if isinstance(data, dict):
        return {k: _render_mode_tokens(v, mode) for k, v in data.items()}
    if isinstance(data, list):
        return [_render_mode_tokens(item, mode) for item in data]
    return data


def _apply_mode_profiles(raw_cfg: dict) -> dict:
    profiles = raw_cfg.get("modes") or raw_cfg.get("mode_profiles")
    if not isinstance(profiles, dict) or not profiles:
        return raw_cfg

    shared = raw_cfg.get("shared") if isinstance(raw_cfg.get("shared"), dict) else {}
    meta_keys = {"default_mode", "active_mode"}
    requested = os.getenv("SLSBOT_MODE") or raw_cfg.get("active_mode") or raw_cfg.get("default_mode")
    if not requested or requested not in profiles:
        requested = next(iter(profiles))

    base_common = {
        k: v
        for k, v in raw_cfg.items()
        if k not in {"modes", "mode_profiles", "shared"} | meta_keys
    }
    selected = profiles.get(requested, {})
    merged = _deep_merge(base_common, shared)
    merged = _deep_merge(merged, selected)
    merged["_active_mode"] = requested
    merged["_available_modes"] = sorted(profiles.keys())
    merged["_mode_config_path"] = raw_cfg.get("_mode_config_path", CFG_PATH_IN_USE)
    merged = _render_mode_tokens(merged, requested)
    return merged

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
            cfg = _json_load_permissive(p)
            return _apply_mode_profiles(cfg)

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
            cfg = _json_load_permissive(c)
            return _apply_mode_profiles(cfg)

    raise FileNotFoundError(
        "No se encontró config.json. Define SLSBOT_CONFIG o coloca el archivo en /config/config.json."
    )
