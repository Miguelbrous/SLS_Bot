from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
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
        promoted = self.manager.promote_winners()
        self._update_state(len(promoted))
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

    def _update_state(self, promoted_count: int) -> None:
        state = self.manager.registry.ensure_state()
        now = datetime.now(timezone.utc)
        iso = now.isoformat().replace("+00:00", "Z")
        state["last_tick_ts"] = iso
        state["updated_at"] = iso
        state["last_tick_promoted"] = promoted_count
        ticks_since_win = 0 if promoted_count else int(state.get("ticks_since_win") or 0) + 1
        state["ticks_since_win"] = ticks_since_win
        top_balances = self.manager.storage.top_balances(limit=1)
        if top_balances:
            top_balance = float(top_balances[0].get("balance_after") or 0.0)
            current_goal = float(state.get("current_goal") or self.manager.cfg.initial_goal)
            if current_goal <= 0:
                current_goal = self.manager.cfg.initial_goal
            drawdown = max(0.0, (current_goal - top_balance) / max(current_goal, 1e-9) * 100.0)
            state["drawdown_pct"] = round(drawdown, 2)
        self.manager.registry.save_state(state)
        self.manager.storage.save_state(state)
