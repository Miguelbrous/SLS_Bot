from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, List, Optional

import requests

try:
    from ..sls_bot import ia_utils
except (ImportError, ValueError):
    from sls_bot import ia_utils  # type: ignore

log = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class NewsAggregatorConfig:
    enabled: bool = False
    provider: str = "cryptopanic"
    api_url: str = "https://cryptopanic.com/api/v1/posts/"
    api_token: Optional[str] = None
    token_env: Optional[str] = None
    min_votes: int = 1
    limit: int = 20

    @classmethod
    def from_dict(cls, data: dict | None) -> "NewsAggregatorConfig":
        if not data:
            return cls()
        token = data.get("api_token")
        token_env = data.get("token_env")
        if not token and token_env:
            token = os.getenv(token_env)
        return cls(
            enabled=bool(data.get("enabled", False)),
            provider=str(data.get("provider") or "cryptopanic"),
            api_url=str(data.get("api_url") or cls.api_url),
            api_token=token,
            token_env=token_env,
            min_votes=int(data.get("min_votes") or 1),
            limit=int(data.get("limit") or 20),
        )


class NewsAggregatorClient:
    def __init__(self, config: dict | None):
        cfg = NewsAggregatorConfig.from_dict(config or {})
        self.config = cfg
        self._sentiment = None
        if cfg.enabled:
            try:
                from .nlp import get_sentiment_analyzer  # lazy import to avoid recursion
            except Exception:  # pragma: no cover
                get_sentiment_analyzer = None  # type: ignore
            if get_sentiment_analyzer:
                self._sentiment = get_sentiment_analyzer()

    def fetch(self, *, limit: int = 20) -> List[dict]:
        cfg = self.config
        if not cfg.enabled or not cfg.api_token:
            return []
        if cfg.provider.lower() != "cryptopanic":
            log.warning("News provider %s not supported yet", cfg.provider)
            return []
        params = {
            "auth_token": cfg.api_token,
            "kind": "news",
            "public": "true",
            "filter": "rising",
            "limit": min(limit, cfg.limit),
        }
        try:
            resp = requests.get(cfg.api_url, params=params, timeout=10)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # pragma: no cover - network failure
            log.warning("News API fetch failed: %s", exc)
            return []
        rows = []
        for item in payload.get("results") or []:
            if cfg.min_votes and (item.get("votes") or {}).get("total", 0) < cfg.min_votes:
                continue
            title = item.get("title") or item.get("slug") or ""
            url = item.get("url") or item.get("source") or ""
            published = item.get("published_at") or item.get("created_at")
            ts = None
            if published:
                try:
                    ts = datetime.fromisoformat(published.replace("Z", "+00:00")).astimezone(timezone.utc)
                except Exception:
                    ts = _utc_now()
            sentiment_score = None
            if self._sentiment:
                try:
                    res = self._sentiment.score(title)
                    sentiment_score = res.compound if res else None
                except Exception:
                    sentiment_score = None
            rows.append(
                {
                    "title": title,
                    "url": url,
                    "published_at": ts,
                    "sentiment": sentiment_score,
                    "source": item.get("site") or "CryptoPanic",
                }
            )
        return rows


@dataclass
class WhaleWatcherConfig:
    enabled: bool = False
    min_notional: float = 1_000_000.0
    orderbook_depth: int = 50
    spoof_ratio: float = 4.0
    imbalance_threshold: float = 0.25
    imbalance_warn: float = 0.25
    imbalance_block: float = 0.6
    allow_spoof_override: bool = False

    @classmethod
    def from_dict(cls, data: dict | None) -> "WhaleWatcherConfig":
        if not data:
            return cls()
        return cls(
            enabled=bool(data.get("enabled", False)),
            min_notional=float(data.get("min_notional") or 1_000_000.0),
            orderbook_depth=int(data.get("orderbook_depth") or 50),
            spoof_ratio=float(data.get("spoof_ratio") or 4.0),
            imbalance_threshold=float(data.get("imbalance_threshold") or 0.25),
            imbalance_warn=float(data.get("imbalance_warn") or data.get("imbalance_threshold") or 0.25),
            imbalance_block=float(data.get("imbalance_block") or 0.6),
            allow_spoof_override=bool(data.get("allow_spoof_override", False)),
        )


class WhaleWatcher:
    def __init__(self, config: dict | None):
        self.config = WhaleWatcherConfig.from_dict(config or {})

    def analyze(self, symbol: str) -> Optional[Dict[str, Any]]:
        cfg = self.config
        if not cfg.enabled:
            return None
        try:
            book = ia_utils.fetch_orderbook(symbol, depth=cfg.orderbook_depth)
        except Exception as exc:
            log.debug("Orderbook fetch failed: %s", exc)
            return None
        bids = [(float(row["price"]), float(row["size"])) for row in book.get("bids", [])]
        asks = [(float(row["price"]), float(row["size"])) for row in book.get("asks", [])]
        if not bids or not asks:
            return None

        bid_notional = [price * size for price, size in bids]
        ask_notional = [price * size for price, size in asks]
        total_bid = sum(bid_notional)
        total_ask = sum(ask_notional)
        imbalance = 0.0
        denom = total_bid + total_ask
        if denom > 0:
            imbalance = (total_bid - total_ask) / denom

        whale_side = None
        whale_notional = 0.0
        if max(bid_notional) >= cfg.min_notional or max(ask_notional) >= cfg.min_notional:
            if max(bid_notional) >= max(ask_notional):
                whale_side = "bid"
                whale_notional = max(bid_notional)
            else:
                whale_side = "ask"
                whale_notional = max(ask_notional)

        spoofing_side = None
        spoofing_flag = False
        if bid_notional:
            bid_median = median(bid_notional)
            if bid_median > 0 and max(bid_notional) / bid_median >= cfg.spoof_ratio:
                spoofing_flag = True
                spoofing_side = "bid"
        if ask_notional:
            ask_median = median(ask_notional)
            if ask_median > 0 and max(ask_notional) / ask_median >= cfg.spoof_ratio and max(ask_notional) > whale_notional:
                spoofing_flag = True
                spoofing_side = "ask"

        severity = abs(imbalance)
        return {
            "imbalance": round(imbalance, 4),
            "whale_side": whale_side,
            "whale_notional": round(whale_notional, 2),
            "spoofing_suspected": spoofing_flag,
            "spoofing_side": spoofing_side,
            "total_bid": round(total_bid, 2),
            "total_ask": round(total_ask, 2),
            "captured_at": _utc_now().isoformat().replace("+00:00", "Z"),
            "severity": severity,
        }
