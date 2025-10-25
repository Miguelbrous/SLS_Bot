from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence

from ..sls_bot.config_loader import load_config


@dataclass
class CerebroConfig:
    symbols: Sequence[str] = field(default_factory=lambda: ["BTCUSDT"])
    timeframes: Sequence[str] = field(default_factory=lambda: ["15m"])
    refresh_seconds: int = 60
    news_feeds: Sequence[str] = field(default_factory=list)
    min_confidence: float = 0.55
    max_memory: int = 5000

    @classmethod
    def from_dict(cls, data: dict) -> "CerebroConfig":
        if not data:
            return cls()
        return cls(
            symbols=data.get("symbols") or ["BTCUSDT"],
            timeframes=data.get("timeframes") or ["15m"],
            refresh_seconds=int(data.get("refresh_seconds") or 60),
            news_feeds=data.get("news_feeds") or [],
            min_confidence=float(data.get("min_confidence") or 0.55),
            max_memory=int(data.get("max_memory") or 5000),
        )


def load_cerebro_config() -> CerebroConfig:
    cfg = load_config()
    cerebro_dict = cfg.get("cerebro") if isinstance(cfg, dict) else None
    return CerebroConfig.from_dict(cerebro_dict or {})
