from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Sequence


def load_rows(dataset_path: Path) -> List[dict]:
    rows: List[dict] = []
    if not dataset_path.exists():
        raise FileNotFoundError(f"No existe el dataset en {dataset_path}")
    with dataset_path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def summarize_rows(rows: Sequence[dict]) -> Dict[str, object]:
    total = len(rows)
    wins = 0
    losses = 0
    longs = 0
    shorts = 0
    symbols: Dict[str, int] = {}
    timeframes: Dict[str, int] = {}

    for item in rows:
        pnl = float(item.get("pnl") or 0.0)
        decision = (item.get("decision") or item.get("side") or "").upper()
        symbol = (item.get("symbol") or item.get("features", {}).get("symbol") or "UNKNOWN").upper()
        timeframe = (item.get("timeframe") or item.get("features", {}).get("timeframe") or "UNKNOWN").lower()

        if pnl > 0:
            wins += 1
        elif pnl < 0:
            losses += 1
        if decision == "LONG":
            longs += 1
        elif decision == "SHORT":
            shorts += 1

        symbols[symbol] = symbols.get(symbol, 0) + 1
        timeframes[timeframe] = timeframes.get(timeframe, 0) + 1

    win_rate = wins / total if total else 0.0
    long_rate = longs / total if total else 0.0
    short_rate = shorts / total if total else 0.0
    dominant_symbol_share = max((count / total for count in symbols.values()), default=0.0)

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "long_rate": long_rate,
        "short_rate": short_rate,
        "symbols": symbols,
        "timeframes": timeframes,
        "dominant_symbol_share": dominant_symbol_share,
    }
