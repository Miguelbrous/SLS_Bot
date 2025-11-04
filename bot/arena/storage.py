from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable, List

from .models import StrategyLedgerEntry

ARENA_DIR = Path(__file__).resolve().parent
DB_PATH = ARENA_DIR / "arena.db"


class ArenaStorage:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_id TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    pnl REAL NOT NULL,
                    balance_after REAL NOT NULL,
                    reason TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_strategy ON ledger(strategy_id)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def append_ledger(self, entries: Iterable[StrategyLedgerEntry]) -> None:
        rows = [
            (
                entry.strategy_id,
                entry.ts,
                entry.pnl,
                entry.balance_after,
                entry.reason,
            )
            for entry in entries
        ]
        if not rows:
            return
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO ledger(strategy_id, ts, pnl, balance_after, reason) VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()

    def save_state(self, state: dict) -> None:
        payload = json.dumps(state, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO state(key, value) VALUES(?, ?)", ("arena_state", payload))
            conn.commit()

    def load_state(self) -> dict:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM state WHERE key = ?", ("arena_state",)).fetchone()
            if not row:
                return {}
            try:
                return json.loads(row["value"])
            except json.JSONDecodeError:
                return {}

    def top_balances(self, limit: int = 200) -> List[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT l.strategy_id, l.ts, l.balance_after
                FROM ledger l
                JOIN (
                    SELECT strategy_id, MAX(id) AS max_id
                    FROM ledger
                    GROUP BY strategy_id
                ) latest ON latest.max_id = l.id
                ORDER BY l.balance_after DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]
