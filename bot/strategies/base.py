from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class StrategyContext:
    balance: float
    mode: str
    symbol: str
    timeframe: str
    leverage: int


class Strategy(abc.ABC):
    id: str = "strategy"
    symbol: str = "BTCUSDT"
    timeframe: str = "15m"

    @abc.abstractmethod
    def build_signal(self, context: StrategyContext) -> Optional[Dict[str, object]]:
        """Returna el cuerpo del webhook listo para enviar."""


class StrategyRegistry:
    _registry: Dict[str, Strategy] = {}

    @classmethod
    def register(cls, strategy: Strategy) -> None:
        cls._registry[strategy.id] = strategy

    @classmethod
    def get(cls, key: str) -> Strategy:
        try:
            return cls._registry[key]
        except KeyError as exc:
            raise ValueError(f"Estrategia desconocida: {key}") from exc

    @classmethod
    def all(cls) -> Dict[str, Strategy]:
        return dict(cls._registry)
