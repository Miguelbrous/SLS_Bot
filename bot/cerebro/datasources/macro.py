from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import copy
import logging

logger = logging.getLogger(__name__)

import requests

from .base import DataSource


@dataclass
class MacroFeedConfig:
    open_interest_url: Optional[str] = None
    funding_rate_url: Optional[str] = None
    whale_flow_url: Optional[str] = None
    cache_dir: Optional[str] = None
    timeout: float = 5.0
    cache_ttl: float = 300.0
    retry_attempts: int = 2

    @classmethod
    def from_dict(cls, data: Dict[str, object] | None) -> "MacroFeedConfig":
        data = data or {}
        return cls(
            open_interest_url=str(data.get("open_interest_url", "") or "") or None,
            funding_rate_url=str(data.get("funding_rate_url", "") or "") or None,
            whale_flow_url=str(data.get("whale_flow_url", "") or "") or None,
            cache_dir=str(data.get("cache_dir", "") or "") or None,
            timeout=float(data.get("timeout", 5.0) or 5.0),
            cache_ttl=float(data.get("cache_ttl", 300.0) or 300.0),
            retry_attempts=int(data.get("retry_attempts", 2) or 2),
        )


class MacroDataSource(DataSource):
    """Obtiene lecturas macro (open interest, funding, whale flow) para el Cerebro."""

    name = "macro"

    def __init__(self, config: MacroFeedConfig | None = None):
        self.config = config or MacroFeedConfig()
        self._http_cache: Dict[str, Tuple[float, List[dict]]] = {}

    def _load_cached(self, cache_file: str) -> List[dict]:
        if not cache_file:
            return []
        path = Path(cache_file)
        if not path.is_absolute() and self.config.cache_dir:
            path = Path(self.config.cache_dir).expanduser().resolve() / path
        if not path.exists():
            return []
        try:
            raw = path.read_text(encoding="utf-8")
            payload = json.loads(raw)
            if isinstance(payload, list):
                return copy.deepcopy(payload)
        except Exception:
            return []
        return []

    def _http_fetch(self, url: Optional[str]) -> List[dict]:
        if not url:
            return []
        cache_entry = self._http_cache.get(url)
        now = time.time()
        if cache_entry and (now - cache_entry[0]) < self.config.cache_ttl:
            return copy.deepcopy(cache_entry[1])
        attempts = max(1, self.config.retry_attempts)
        last_error: Optional[Exception] = None
        for attempt in range(attempts):
            try:
                resp = requests.get(url, timeout=self.config.timeout)
                resp.raise_for_status()
                payload = resp.json()
                if isinstance(payload, list):
                    self._http_cache[url] = (now, payload)
                    return copy.deepcopy(payload)
                if isinstance(payload, dict):
                    data = [payload]
                    self._http_cache[url] = (now, data)
                    return copy.deepcopy(data)
            except Exception as exc:
                last_error = exc
                time.sleep(0.2 * (attempt + 1))
        if last_error:
            logger.debug("MacroDataSource: fallo al consultar %s: %s", url, last_error)
        return []

    def _fallback_payload(self) -> List[dict]:
        ts = int(time.time())
        # Genera un payload sintético mínima para no romper el pipeline.
        return [
            {
                "ts": ts,
                "symbol": "BTCUSDT",
                "open_interest_change_pct": random.uniform(-0.5, 0.5),
                "funding_rate": random.uniform(-0.0005, 0.0005),
                "whale_txs": random.randint(0, 5),
            }
        ]

    def fetch(self, *, symbol: str | None = None, timeframe: str | None = None, limit: int = 50) -> List[dict]:
        rows: List[dict] = []
        cache_dir = self.config.cache_dir
        cache_file = None
        if cache_dir:
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            cache_file = os.path.join(cache_dir, f"macro_cache_{symbol or 'ALL'}.json")

        oi_rows = self._http_fetch(self.config.open_interest_url)
        fr_rows = self._http_fetch(self.config.funding_rate_url)
        whale_rows = self._http_fetch(self.config.whale_flow_url)
        if not oi_rows and cache_file:
            oi_rows = self._load_cached(cache_file)

        combined: Dict[str, dict] = {}
        for item in oi_rows:
            key = (item.get("symbol") or symbol or "ALL").upper()
            combined.setdefault(key, {}).update(item)
        for item in fr_rows:
            key = (item.get("symbol") or symbol or "ALL").upper()
            combined.setdefault(key, {}).update(item)
        for item in whale_rows:
            key = (item.get("symbol") or symbol or "ALL").upper()
            combined.setdefault(key, {}).update(item)

        rows = [
            {
                "symbol": key,
                "open_interest_change_pct": float(payload.get("open_interest_change_pct") or 0.0),
                "funding_rate": float(payload.get("funding_rate") or 0.0),
                "whale_txs": int(payload.get("whale_txs") or 0),
                "ts": int(payload.get("ts") or time.time()),
            }
            for key, payload in combined.items()
        ]

        if not rows:
            rows = self._fallback_payload()

        if cache_file:
            try:
                Path(cache_file).write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass

        if symbol:
            symbol_upper = symbol.upper()
            rows = [row for row in rows if row.get("symbol") == symbol_upper] or rows
        return rows[:limit]
