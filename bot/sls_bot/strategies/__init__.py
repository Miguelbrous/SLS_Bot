"""Strategy registry for SLS bot."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .scalping import ScalpingStrategy


_SCALPING_INSTANCE: Optional[ScalpingStrategy] = None


def get_scalping_strategy(config: Dict[str, Any]) -> ScalpingStrategy:
    global _SCALPING_INSTANCE
    if _SCALPING_INSTANCE is None:
        _SCALPING_INSTANCE = ScalpingStrategy(config)
    else:
        _SCALPING_INSTANCE.update_config(config)
    return _SCALPING_INSTANCE


__all__ = ["get_scalping_strategy", "ScalpingStrategy"]
