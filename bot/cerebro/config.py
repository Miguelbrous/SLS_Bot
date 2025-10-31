from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

try:
    from ..sls_bot.config_loader import load_config
except ImportError:  # pragma: no cover
    from sls_bot.config_loader import load_config  # type: ignore
from .filters import SessionGuardConfig


DEFAULT_SESSION_GUARDS = [
    {
        "name": "Asia (Tokyo)",
        "timezone": "Asia/Tokyo",
        "open_time": "09:00",
        "pre_open_minutes": 45,
        "post_open_minutes": 30,
        "wait_for_news_minutes": 45,
    },
    {
        "name": "Europa (Londres)",
        "timezone": "Europe/London",
        "open_time": "08:00",
        "pre_open_minutes": 45,
        "post_open_minutes": 45,
        "wait_for_news_minutes": 60,
    },
    {
        "name": "America (Nueva York)",
        "timezone": "America/New_York",
        "open_time": "09:30",
        "pre_open_minutes": 60,
        "post_open_minutes": 60,
        "wait_for_news_minutes": 60,
    },
]


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
    news_ttl_minutes: int = 45
    session_guards: Sequence[SessionGuardConfig] = field(default_factory=list)
    data_cache_ttl: int = 30
    anomaly_z_threshold: float = 3.0
    anomaly_min_points: int = 20
    confidence_max: float = 0.7
    confidence_min: float = 0.45
    auto_train_interval: int = 100

    @classmethod
    def from_dict(cls, data: dict) -> "CerebroConfig":
        if not data:
            return cls()
        raw_sessions = data.get("session_guards") or DEFAULT_SESSION_GUARDS
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
            news_ttl_minutes=int(data.get("news_ttl_minutes") or 45),
            session_guards=[SessionGuardConfig.from_dict(item or {}) for item in raw_sessions],
            data_cache_ttl=int(data.get("data_cache_ttl") or 30),
            anomaly_z_threshold=float(data.get("anomaly_z_threshold") or 3.0),
            anomaly_min_points=int(data.get("anomaly_min_points") or 20),
            confidence_max=float(data.get("confidence_max") or 0.7),
            confidence_min=float(data.get("confidence_min") or 0.45),
            auto_train_interval=int(data.get("auto_train_interval") or 100),
        )


def load_cerebro_config() -> CerebroConfig:
    cfg = load_config()
    cerebro_dict = cfg.get("cerebro") if isinstance(cfg, dict) else None
    return CerebroConfig.from_dict(cerebro_dict or {})
