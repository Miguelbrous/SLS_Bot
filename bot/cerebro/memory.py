from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List


@dataclass
class Experience:
    """Representa una operación real del bot."""

    symbol: str
    timeframe: str
    pnl: float
    features: Dict[str, float]
    decision: str


class ExperienceMemory:
    def __init__(self, maxlen: int = 5000):
        self.buffer: Deque[Experience] = deque(maxlen=maxlen)

    def push(self, exp: Experience) -> None:
        self.buffer.append(exp)

    def last(self, limit: int = 50) -> List[Experience]:
        return list(self.buffer)[-limit:]

    def stats(self) -> dict:
        wins = sum(1 for e in self.buffer if e.pnl > 0)
        losses = sum(1 for e in self.buffer if e.pnl < 0)
        return {
            "total": len(self.buffer),
            "wins": wins,
            "losses": losses,
            "win_rate": wins / len(self.buffer) if self.buffer else 0.0,
        }
