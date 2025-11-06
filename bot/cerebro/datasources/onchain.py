from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


@dataclass
class OnchainFeedConfig:
    base_url: str = "https://api.blockchair.com"
    timeout: float = 5.0
    retry_attempts: int = 2
    cache_ttl: float = 180.0
    enabled: bool = False
    assets: Dict[str, str] = field(
        default_factory=lambda: {
            "BTCUSDT": "bitcoin",
            "ETHUSDT": "ethereum",
        }
    )
    inflow_threshold: float = 0.05

    @classmethod
    def from_dict(cls, data: Dict[str, object] | None) -> "OnchainFeedConfig":
        data = data or {}
        assets = data.get("assets") or {"BTCUSDT": "bitcoin", "ETHUSDT": "ethereum"}
        return cls(
            base_url=str(data.get("base_url") or "https://api.blockchair.com"),
            timeout=float(data.get("timeout") or 5.0),
            retry_attempts=int(data.get("retry_attempts") or 2),
            cache_ttl=float(data.get("cache_ttl") or 180.0),
            enabled=bool(data.get("enabled", False)),
            assets={k.upper(): str(v) for k, v in assets.items()},
            inflow_threshold=float(data.get("inflow_threshold") or 0.05),
        )


class OnchainDataSource:
    name = "onchain"

    def __init__(self, config: OnchainFeedConfig | None = None) -> None:
        self.config = config or OnchainFeedConfig()
        self._cache: Dict[str, Tuple[float, List[dict]]] = {}

    def _cached(self, symbol: str) -> Optional[List[dict]]:
        entry = self._cache.get(symbol)
        if not entry:
            return None
        ts, payload = entry
        if time.time() - ts > self.config.cache_ttl:
            return None
        return copy.deepcopy(payload)

    def _store(self, symbol: str, payload: List[dict]) -> List[dict]:
        self._cache[symbol] = (time.time(), payload)
        return copy.deepcopy(payload)

    def _http_fetch(self, asset: str) -> Optional[dict]:
        url = f"{self.config.base_url.rstrip('/')}/{asset}/stats"
        last_error: Optional[Exception] = None
        for attempt in range(max(1, self.config.retry_attempts)):
            try:
                resp = requests.get(url, timeout=self.config.timeout)
                resp.raise_for_status()
                payload = resp.json()
                return payload.get("data") or {}
            except Exception as exc:  # pragma: no cover - network
                last_error = exc
                time.sleep(0.2 * (attempt + 1))
        if last_error:
            logger.debug("OnchainDataSource error: %s", last_error)
        return None

    def fetch(self, *, symbol: str | None = None, timeframe: str | None = None, limit: int = 1) -> List[dict]:
        if not symbol:
            raise ValueError("OnchainDataSource requiere symbol")
        symbol = symbol.upper()
        if not self.config.enabled:
            return [self._fallback(symbol)]
        cached = self._cached(symbol)
        if cached is not None:
            return cached
        asset = self.config.assets.get(symbol)
        if not asset:
            return self._store(symbol, [self._fallback(symbol)])
        raw = self._http_fetch(asset) or {}
        summary = self._summarize(symbol, raw)
        return self._store(symbol, [summary])

    def _summarize(self, symbol: str, payload: dict) -> dict:
        stats = payload.get("data", payload)
        mempool_txs = float(stats.get("mempool_transactions") or 0.0)
        tx_24h = float(stats.get("transactions_24h") or 0.0)
        hash_rate = float(stats.get("hash_rate_24h") or 0.0)
        fees_24h_usd = float(stats.get("fees_24h_usd") or 0.0)
        active_addresses = float(stats.get("transactions_last_24_hours") or stats.get("addresses_active_24h") or 0.0)
        mempool_ratio = mempool_txs / max(tx_24h, 1.0)
        whale_bias = "neutral"
        threshold = self.config.inflow_threshold
        if mempool_ratio > threshold:
            whale_bias = "sell_pressure"
        elif mempool_ratio < threshold / 2:
            whale_bias = "buy_pressure"
        return {
            "symbol": symbol,
            "mempool_transactions": mempool_txs,
            "transactions_24h": tx_24h,
            "hash_rate_24h": hash_rate,
            "fees_24h_usd": fees_24h_usd,
            "active_addresses": active_addresses,
            "mempool_ratio": mempool_ratio,
            "whale_bias": whale_bias,
            "threshold": threshold,
            "ts": int(time.time()),
        }

    def _fallback(self, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "mempool_transactions": 0.0,
            "transactions_24h": 0.0,
            "hash_rate_24h": 0.0,
            "fees_24h_usd": 0.0,
            "active_addresses": 0.0,
            "mempool_ratio": 0.0,
            "whale_bias": "neutral",
            "threshold": self.config.inflow_threshold,
            "ts": int(time.time()),
        }
