from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Deque, Dict, List, Tuple


@dataclass
class FeatureSlice:
    symbol: str
    timeframe: str
    data: List[dict]
    normalized: List[dict] = field(default_factory=list)


@dataclass
class FeatureStats:
    count: int = 0
    means: Dict[str, float] = field(default_factory=dict)
    vars: Dict[str, float] = field(default_factory=dict)

    def update(self, rows: List[dict]) -> None:
        if not rows:
            return
        numeric_keys = {
            key
            for row in rows
            for key, value in row.items()
            if isinstance(value, (int, float))
        }
        for key in numeric_keys:
            series = [float(row.get(key, 0.0)) for row in rows]
            self.means[key] = mean(series)
            self.vars[key] = pstdev(series) or 1.0
        self.count += len(rows)

    def normalize(self, row: dict) -> dict:
        normalized = {}
        for key, value in row.items():
            if not isinstance(value, (int, float)):
                continue
            mu = self.means.get(key, 0.0)
            sigma = self.vars.get(key, 1.0)
            if sigma == 0:
                sigma = 1.0
            normalized[key] = (float(value) - mu) / sigma
        return normalized


class FeatureStore:
    """Cache liviana en memoria para que el Cerebro pueda consultar rápidamente."""

    def __init__(self, maxlen: int = 500):
        self.maxlen = maxlen
        self._store: Dict[str, Deque[dict]] = defaultdict(lambda: deque(maxlen=self.maxlen))
        self._stats: Dict[str, FeatureStats] = defaultdict(FeatureStats)

    def key(self, symbol: str, timeframe: str) -> str:
        return f"{symbol.upper()}::{timeframe}"

    def update(self, symbol: str, timeframe: str, rows: List[dict]) -> None:
        bucket = self._store[self.key(symbol, timeframe)]
        for row in rows:
            bucket.append(row)
        self._stats[self.key(symbol, timeframe)].update(list(bucket))

    def latest(self, symbol: str, timeframe: str, window: int = 50) -> FeatureSlice:
        bucket = list(self._store.get(self.key(symbol, timeframe), []))
        stats = self._stats.get(self.key(symbol, timeframe))
        normalized = []
        if stats:
            normalized = [stats.normalize(row) for row in bucket[-window:]]
        return FeatureSlice(symbol=symbol.upper(), timeframe=timeframe, data=bucket[-window:], normalized=normalized)

    def stats(self) -> dict:
        return {
            key: {
                "size": len(values),
                "features_tracked": list(self._stats[key].means.keys()),
            }
            for key, values in self._store.items()
        }

    def describe(self, symbol: str, timeframe: str) -> Tuple[dict, dict]:
        stats = self._stats.get(self.key(symbol, timeframe))
        if not stats:
            return {}, {}
        return dict(stats.means), dict(stats.vars)
