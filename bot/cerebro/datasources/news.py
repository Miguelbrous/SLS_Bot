from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import List, Sequence
from xml.etree import ElementTree

import requests

from .base import DataSource, NewsItem
from ..nlp import get_sentiment_analyzer

log = logging.getLogger(__name__)


class RSSNewsDataSource(DataSource):
    """Lectura simple de feeds RSS (sin dependencias extras)."""

    name = "news"

    def __init__(self, feeds: Sequence[str]):
        self.feeds = list(feeds) or []
        self._sentiment = get_sentiment_analyzer()
        self._error_backoff: dict[str, float] = {}

    def fetch(self, *, symbol: str | None = None, timeframe: str | None = None, limit: int = 20) -> List[dict]:
        items: List[dict] = []
        for url in self.feeds:
            try:
                resp = requests.get(url, timeout=10)
                resp.raise_for_status()
                root = ElementTree.fromstring(resp.content)
                for entry in root.findall(".//item")[:limit]:
                    title = (entry.findtext("title") or "").strip()
                    link = (entry.findtext("link") or "").strip()
                    pub = entry.findtext("pubDate")
                    ts = None
                    if pub:
                        try:
                            ts = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z").astimezone(timezone.utc)
                        except Exception:
                            ts = datetime.now(timezone.utc)
                    sentiment_score = None
                    if self._sentiment:
                        res = self._sentiment.score(title)
                        if res:
                            sentiment_score = res.compound
                    items.append(
                        NewsItem(title=title, url=link, published_at=ts, sentiment=sentiment_score).__dict__
                    )
            except Exception as exc:
                now = time.time()
                last = self._error_backoff.get(url, 0.0)
                if now - last >= 300:
                    log.warning("RSS fetch failed for %s (backoff 5m): %s", url, exc)
                    self._error_backoff[url] = now
                else:
                    log.debug("RSS fetch failed for %s (silenced): %s", url, exc)
        return items[:limit]
