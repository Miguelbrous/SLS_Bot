from .base import Strategy, StrategyContext, StrategyRegistry
from .micro_scalp import MicroScalpStrategy
from .scalp_rush import ScalpRushStrategy

StrategyRegistry.register(MicroScalpStrategy())
StrategyRegistry.register(ScalpRushStrategy())

__all__ = [
    "Strategy",
    "StrategyContext",
    "StrategyRegistry",
    "MicroScalpStrategy",
    "ScalpRushStrategy",
]
