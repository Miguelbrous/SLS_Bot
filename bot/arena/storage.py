from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
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
                "CREATE INDEX IF NOT EXISTS idx_ledger_strategy_id ON ledger(strategy_id, id DESC)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_id TEXT NOT NULL,
                    note TEXT NOT NULL,
                    author TEXT,
                    ts TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_notes_strategy ON notes(strategy_id)")
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

    def ledger_for(self, strategy_id: str, limit: int | None = 50) -> List[dict]:
        query = """
            SELECT strategy_id, ts, pnl, balance_after, reason
            FROM (
                SELECT strategy_id, ts, pnl, balance_after, reason
                FROM ledger
                WHERE strategy_id = ?
                ORDER BY id DESC
                {limit_clause}
            )
            ORDER BY ts ASC
        """
        limit_clause = "LIMIT ?" if limit else ""
        sql = query.format(limit_clause=limit_clause)
        params: tuple = (strategy_id,) if not limit else (strategy_id, limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    def ledger_summary(self, strategy_id: str, limit: int | None = None) -> dict:
        rows = self.ledger_for(strategy_id, limit=limit)
        if not rows:
            return {}
        total = len(rows)
        total_pnl = sum(entry["pnl"] for entry in rows)
        wins = sum(1 for entry in rows if entry["pnl"] > 0)
        losses = total - wins
        avg_pnl = total_pnl / total if total else 0.0
        win_rate = (wins / total) * 100 if total else 0.0
        balances = [entry["balance_after"] for entry in rows]
        final_balance = balances[-1]
        peak = -float("inf")
        max_drawdown = 0.0
        for bal in balances:
            peak = max(peak, bal)
            if peak > 0:
                drawdown = (peak - bal) / peak * 100
                max_drawdown = max(max_drawdown, drawdown)
        return {
            "strategy_id": strategy_id,
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "avg_pnl": avg_pnl,
            "final_balance": final_balance,
            "max_drawdown_pct": max_drawdown,
        }

    def add_note(self, strategy_id: str, note: str, author: str | None = None) -> dict:
        ts = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO notes(strategy_id, note, author, ts) VALUES (?, ?, ?, ?)",
                (strategy_id, note, author, ts),
            )
            conn.commit()
        return {"strategy_id": strategy_id, "note": note, "author": author, "ts": ts}

    def notes_for(self, strategy_id: str, limit: int = 20) -> List[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT strategy_id, note, author, ts
                FROM notes
                WHERE strategy_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (strategy_id, limit),
            ).fetchall()
            data = [dict(row) for row in rows]
            data.reverse()
            return data
