from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Protocol


class DataSource(Protocol):
    name: str

    def fetch(self, *, symbol: str | None = None, timeframe: str | None = None, limit: int = 200) -> List[dict]:
        """Obtiene datos crudos para el cerebro."""
        raise NotImplementedError


@dataclass
class NewsItem:
    title: str
    url: str
    published_at: datetime | None = None
    sentiment: str | None = None
