from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Iterable, List, Optional, Tuple

from .datasources.market import MarketDataSource
from .datasources.macro import MacroDataSource, MacroFeedConfig
from .datasources.news import RSSNewsDataSource
from .datasources.orderflow import OrderflowDataSource, OrderflowConfig
from .datasources.funding import FundingDataSource, FundingFeedConfig
from .datasources.onchain import OnchainDataSource, OnchainFeedConfig


@dataclass
class IngestionTask:
    source: str
    symbol: str | None = None
    timeframe: str | None = None
    limit: int = 200
    created_at: float = field(default_factory=lambda: time.time())


class DataIngestionManager:
    """Administra los data sources con un buffer FIFO y caching básico."""

    def __init__(
        self,
        *,
        news_feeds: Iterable[str],
        cache_ttl: int = 30,
        macro_config: dict | None = None,
        orderflow_config: dict | None = None,
        funding_config: dict | None = None,
        onchain_config: dict | None = None,
    ):
        self.market = MarketDataSource()
        self.news = RSSNewsDataSource(list(news_feeds))
        self.macro = MacroDataSource(MacroFeedConfig.from_dict(macro_config))
        self.orderflow = OrderflowDataSource(OrderflowConfig.from_dict(orderflow_config))
        self.funding = FundingDataSource(FundingFeedConfig.from_dict(funding_config))
        self.onchain = OnchainDataSource(OnchainFeedConfig.from_dict(onchain_config))
        self.cache_ttl = cache_ttl
        self._queue: Deque[IngestionTask] = deque()
        self._cache: Dict[Tuple[str, str, str], Tuple[float, List[dict]]] = {}

    def schedule(self, task: IngestionTask) -> None:
        self._queue.append(task)

    def warmup(self, symbols: Iterable[str], timeframes: Iterable[str]) -> None:
        for symbol in symbols:
            for tf in timeframes:
                self.schedule(IngestionTask(source="market", symbol=symbol, timeframe=tf))

    def _cache_key(self, source: str, symbol: str | None, timeframe: str | None) -> Tuple[str, str, str]:
        return (
            source,
            symbol.upper() if symbol else "_",
            timeframe or "_",
        )

    def _get_from_cache(self, key: Tuple[str, str, str]) -> Optional[List[dict]]:
        payload = self._cache.get(key)
        if not payload:
            return None
        ts, data = payload
        if time.time() - ts > self.cache_ttl:
            return None
        return data

    def _store_cache(self, key: Tuple[str, str, str], rows: List[dict]) -> List[dict]:
        self._cache[key] = (time.time(), rows)
        return rows

    def fetch_now(self, source: str, *, symbol: str | None = None, timeframe: str | None = None, limit: int = 200) -> List[dict]:
        key = self._cache_key(source, symbol, timeframe)
        cached = self._get_from_cache(key)
        if cached is not None:
            return cached
        if source == "market":
            rows = self.market.fetch(symbol=symbol, timeframe=timeframe, limit=limit)
            return self._store_cache(key, rows)
        if source == "news":
            rows = self.news.fetch(limit=limit)
            return self._store_cache(key, rows)
        if source == "macro":
            rows = self.macro.fetch(symbol=symbol, timeframe=timeframe, limit=limit)
            return self._store_cache(key, rows)
        if source == "orderflow":
            rows = self.orderflow.fetch(symbol=symbol, timeframe=timeframe, limit=limit)
            return self._store_cache(key, rows)
        if source == "funding":
            rows = self.funding.fetch(symbol=symbol, timeframe=timeframe, limit=limit)
            return self._store_cache(key, rows)
        if source == "onchain":
            rows = self.onchain.fetch(symbol=symbol, timeframe=timeframe, limit=limit)
            return self._store_cache(key, rows)
        raise ValueError(f"Fuente desconocida: {source}")

    def poll(self) -> Optional[IngestionTask]:
        if not self._queue:
            return None
        return self._queue.popleft()

    def run_pending(self, *, max_tasks: int = 10) -> Dict[str, List[dict]]:
        results: Dict[str, List[dict]] = {}
        tasks_run = 0
        while self._queue and tasks_run < max_tasks:
            task = self._queue.popleft()
            rows = self.fetch_now(
                task.source,
                symbol=task.symbol,
                timeframe=task.timeframe,
                limit=task.limit,
            )
            key = f"{task.source}:{task.symbol or ''}:{task.timeframe or ''}"
            results[key] = rows
            tasks_run += 1
        return results
