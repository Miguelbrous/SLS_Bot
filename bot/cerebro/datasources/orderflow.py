from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


@dataclass
class OrderflowConfig:
    base_url: str = "https://api.bybit.com"
    category: str = "linear"
    timeout: float = 5.0
    depth: int = 50
    cache_ttl: float = 10.0
    retry_attempts: int = 2
    enabled: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, object] | None) -> "OrderflowConfig":
        data = data or {}
        return cls(
            base_url=str(data.get("base_url", "https://api.bybit.com") or "https://api.bybit.com"),
            category=str(data.get("category", "linear") or "linear"),
            timeout=float(data.get("timeout", 5.0) or 5.0),
            depth=int(data.get("depth", 50) or 50),
            cache_ttl=float(data.get("cache_ttl", 10.0) or 10.0),
            retry_attempts=int(data.get("retry_attempts", 2) or 2),
            enabled=bool(data.get("enabled", False)),
        )


class OrderflowDataSource:
    name = "orderflow"

    def __init__(self, config: OrderflowConfig | None = None) -> None:
        self.config = config or OrderflowConfig()
        self._cache: Dict[str, Tuple[float, List[dict]]] = {}

    def _cached(self, symbol: str) -> Optional[List[dict]]:
        entry = self._cache.get(symbol)
        if not entry:
            return None
        ts, data = entry
        if time.time() - ts > self.config.cache_ttl:
            return None
        return copy.deepcopy(data)

    def _store(self, symbol: str, payload: List[dict]) -> List[dict]:
        self._cache[symbol] = (time.time(), payload)
        return copy.deepcopy(payload)

    def _http_fetch(self, symbol: str) -> Optional[dict]:
        url = f"{self.config.base_url.rstrip('/')}/v5/market/orderbook"
        params = {
            "category": self.config.category,
            "symbol": symbol.upper(),
            "limit": min(max(1, self.config.depth), 200),
        }
        last_error: Optional[Exception] = None
        for attempt in range(max(1, self.config.retry_attempts)):
            try:
                resp = requests.get(url, params=params, timeout=self.config.timeout)
                resp.raise_for_status()
                payload = resp.json()
                if payload.get("retCode") != 0:
                    raise RuntimeError(payload)
                return payload.get("result") or {}
            except Exception as exc:  # pragma: no cover - red
                last_error = exc
                time.sleep(0.2 * (attempt + 1))
        if last_error:
            logger.debug("OrderflowDataSource error: %s", last_error)
        return None

    def fetch(self, *, symbol: str | None = None, timeframe: str | None = None, limit: int = 1) -> List[dict]:
        if not symbol:
            raise ValueError("OrderflowDataSource requiere symbol")
        if not self.config.enabled:
            return self._store(symbol, [self._fallback(symbol)])
        cached = self._cached(symbol)
        if cached is not None:
            return cached
        raw = self._http_fetch(symbol) or {}
        asks = raw.get("a") or raw.get("asks") or []
        bids = raw.get("b") or raw.get("bids") or []

        def _aggregate(levels: List[List[str]]) -> Tuple[float, float]:
            total_price = 0.0
            total_qty = 0.0
            for entry in levels:
                if len(entry) < 2:
                    continue
                price = float(entry[0])
                qty = float(entry[1])
                total_price += price * qty
                total_qty += qty
            return total_price, total_qty

        bid_price_sum, bid_qty = _aggregate(bids)
        ask_price_sum, ask_qty = _aggregate(asks)
        best_bid = float(bids[0][0]) if bids else None
        best_ask = float(asks[0][0]) if asks else None
        spread = None
        mid = None
        if best_bid is not None and best_ask is not None:
            spread = best_ask - best_bid
            mid = (best_bid + best_ask) / 2.0
        imbalance = 0.0
        if bid_qty + ask_qty > 0:
            imbalance = (bid_qty - ask_qty) / (bid_qty + ask_qty)
        payload = [
            {
                "symbol": symbol.upper(),
                "ts": int(time.time()),
                "best_bid": best_bid,
                "best_ask": best_ask,
                "mid_price": mid,
                "spread": spread,
                "bid_liquidity": bid_qty,
                "ask_liquidity": ask_qty,
                "liquidity_imbalance": imbalance,
            }
        ]
        return self._store(symbol, payload)

    def _fallback(self, symbol: str) -> dict:
        return {
            "symbol": symbol.upper(),
            "ts": int(time.time()),
            "best_bid": None,
            "best_ask": None,
            "mid_price": None,
            "spread": None,
            "bid_liquidity": 0.0,
            "ask_liquidity": 0.0,
            "liquidity_imbalance": 0.0,
        }
