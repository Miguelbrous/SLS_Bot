from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, List


@dataclass
class FeatureSlice:
    symbol: str
    timeframe: str
    data: List[dict]


class FeatureStore:
    """Cache liviana en memoria para que el Cerebro pueda consultar rápidamente."""

    def __init__(self, maxlen: int = 500):
        self.maxlen = maxlen
        self._store: Dict[str, Deque[dict]] = defaultdict(lambda: deque(maxlen=self.maxlen))

    def key(self, symbol: str, timeframe: str) -> str:
        return f"{symbol.upper()}::{timeframe}"

    def update(self, symbol: str, timeframe: str, rows: List[dict]) -> None:
        bucket = self._store[self.key(symbol, timeframe)]
        for row in rows:
            bucket.append(row)

    def latest(self, symbol: str, timeframe: str, window: int = 50) -> FeatureSlice:
        bucket = list(self._store.get(self.key(symbol, timeframe), []))
        return FeatureSlice(symbol=symbol.upper(), timeframe=timeframe, data=bucket[-window:])

    def stats(self) -> dict:
        return {key: len(values) for key, values in self._store.items()}
