from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence

from ..sls_bot.config_loader import load_config
from .filters import SessionGuardConfig


@dataclass
class CerebroConfig:
    enabled: bool = False
    symbols: Sequence[str] = field(default_factory=lambda: ["BTCUSDT"])
    timeframes: Sequence[str] = field(default_factory=lambda: ["15m"])
    refresh_seconds: int = 60
    news_feeds: Sequence[str] = field(default_factory=list)
    min_confidence: float = 0.55
    max_memory: int = 5000
    sl_atr_multiple: float = 1.5
    tp_atr_multiple: float = 2.0

    @classmethod
    def from_dict(cls, data: dict) -> "CerebroConfig":
        if not data:
            return cls()
        return cls(
            enabled=bool(data.get("enabled", False)),
            symbols=data.get("symbols") or ["BTCUSDT"],
            timeframes=data.get("timeframes") or ["15m"],
            refresh_seconds=int(data.get("refresh_seconds") or 60),
            news_feeds=data.get("news_feeds") or [],
            min_confidence=float(data.get("min_confidence") or 0.55),
            max_memory=int(data.get("max_memory") or 5000),
            sl_atr_multiple=float(data.get("sl_atr_multiple") or 1.5),
            tp_atr_multiple=float(data.get("tp_atr_multiple") or 2.0),
        )


def load_cerebro_config() -> CerebroConfig:
    cfg = load_config()
    cerebro_dict = cfg.get("cerebro") if isinstance(cfg, dict) else None
    return CerebroConfig.from_dict(cerebro_dict or {})
