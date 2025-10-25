from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Sequence
from xml.etree import ElementTree

import requests

from .base import DataSource, NewsItem

log = logging.getLogger(__name__)


class RSSNewsDataSource(DataSource):
    """Lectura simple de feeds RSS (sin dependencias extras)."""

    name = "news"

    def __init__(self, feeds: Sequence[str]):
        self.feeds = list(feeds) or []

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
                    items.append(
                        NewsItem(title=title, url=link, published_at=ts, sentiment=None).__dict__
                    )
            except Exception as exc:
                log.warning("RSS fetch failed for %s: %s", url, exc)
        return items[:limit]
