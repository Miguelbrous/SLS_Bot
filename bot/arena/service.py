from __future__ import annotations

import threading
import time
from typing import Optional

from .league_manager import LeagueManager
from .ranking import generate_ranking


class ArenaService:
    """Servicio liviano que ejecuta la arena de forma periódica."""

    def __init__(self, *, interval_seconds: int = 300) -> None:
        self.interval_seconds = max(30, interval_seconds)
        self.manager = LeagueManager()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def tick(self) -> None:
        self.manager.run_tick()
        self.manager.promote_winners()
        generate_ranking()

    def run_forever(self) -> None:
        try:
            while not self._stop_event.is_set():
                self.tick()
                self._stop_event.wait(self.interval_seconds)
        finally:
            generate_ranking()

    def start_background(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.run_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
            self._thread = None
