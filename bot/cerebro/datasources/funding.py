from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


@dataclass
class FundingFeedConfig:
    base_url: str = "https://api.bybit.com"
    category: str = "linear"
    timeout: float = 5.0
    retry_attempts: int = 2
    enabled: bool = False
    cache_ttl: float = 120.0
    threshold: float = 0.00025
    history_limit: int = 24

    @classmethod
    def from_dict(cls, data: Dict[str, object] | None) -> "FundingFeedConfig":
        data = data or {}
        return cls(
            base_url=str(data.get("base_url") or "https://api.bybit.com"),
            category=str(data.get("category") or "linear"),
            timeout=float(data.get("timeout") or 5.0),
            retry_attempts=int(data.get("retry_attempts") or 2),
            enabled=bool(data.get("enabled", False)),
            cache_ttl=float(data.get("cache_ttl") or 120.0),
            threshold=float(data.get("threshold") or 0.00025),
            history_limit=int(data.get("history_limit") or 24),
        )


class FundingDataSource:
    """Consulta el historial de funding y resume sesgo long/short."""

    name = "funding"

    def __init__(self, config: FundingFeedConfig | None = None) -> None:
        self.config = config or FundingFeedConfig()
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

    def _http_fetch(self, symbol: str) -> Optional[List[dict]]:
        url = f"{self.config.base_url.rstrip('/')}/v5/market/funding/history"
        params = {
            "category": self.config.category,
            "symbol": symbol.upper(),
            "limit": min(max(5, self.config.history_limit), 200),
        }
        last_error: Optional[Exception] = None
        for attempt in range(max(1, self.config.retry_attempts)):
            try:
                resp = requests.get(url, params=params, timeout=self.config.timeout)
                resp.raise_for_status()
                payload = resp.json()
                result = payload.get("result") or {}
                rows = result.get("list") or []
                if isinstance(rows, list):
                    return rows
            except Exception as exc:  # pragma: no cover - network errors
                last_error = exc
                time.sleep(0.2 * (attempt + 1))
        if last_error:
            logger.debug("FundingDataSource error: %s", last_error)
        return None

    def fetch(self, *, symbol: str | None = None, timeframe: str | None = None, limit: int = 1) -> List[dict]:
        if not symbol:
            raise ValueError("FundingDataSource requiere symbol")
        symbol = symbol.upper()
        if not self.config.enabled:
            return [self._fallback(symbol)]
        cached = self._cached(symbol)
        if cached is not None:
            return cached
        rows = self._http_fetch(symbol) or []
        summary = self._summarize(symbol, rows)
        return self._store(symbol, [summary])

    def _summarize(self, symbol: str, rows: List[dict]) -> dict:
        if not rows:
            return self._fallback(symbol)
        rates: List[float] = []
        timestamps: List[int] = []
        for item in rows[: self.config.history_limit]:
            try:
                rate = float(item.get("fundingRate") or 0.0)
            except (TypeError, ValueError):
                rate = 0.0
            rates.append(rate)
            try:
                ts = int(item.get("fundingRateTimestamp") or 0)
            except (TypeError, ValueError):
                ts = 0
            timestamps.append(ts)
        last_rate = rates[0] if rates else 0.0
        avg_rate = sum(rates) / len(rates) if rates else 0.0
        bias = "neutral"
        threshold = abs(self.config.threshold)
        if last_rate > threshold:
            bias = "longs_pay"
        elif last_rate < -threshold:
            bias = "shorts_pay"
        hours_since_last = 0.0
        if timestamps and timestamps[0]:
            hours_since_last = max(0.0, (time.time() - timestamps[0] / 1000.0) / 3600.0)
        return {
            "symbol": symbol,
            "last_rate": last_rate,
            "avg_rate": avg_rate,
            "abs_avg_rate": sum(abs(r) for r in rates) / len(rates) if rates else 0.0,
            "bias": bias,
            "history": len(rates),
            "hours_since_last": hours_since_last,
            "threshold": threshold,
            "ts": int(time.time()),
        }

    def _fallback(self, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "last_rate": 0.0,
            "avg_rate": 0.0,
            "abs_avg_rate": 0.0,
            "bias": "neutral",
            "history": 0,
            "hours_since_last": None,
            "threshold": self.config.threshold,
            "ts": int(time.time()),
        }
