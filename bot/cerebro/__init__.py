"""Cerebro IA package.

Expone un singleton `get_cerebro()` para reutilizar un mismo motor en toda la API.
"""

from .service import Cerebro, get_cerebro

__all__ = ["Cerebro", "get_cerebro"]
