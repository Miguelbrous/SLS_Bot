#!/usr/bin/env python3
"""Genera o actualiza el registro con 5 000 estrategias para la arena."""

from __future__ import annotations

import argparse
import itertools
import random
from pathlib import Path
from typing import List

from bot.arena.models import StrategyProfile, StrategyStats
from bot.arena.registry import ArenaRegistry
from bot.arena.config import load_cup_config

CATEGORIES = [
    ("scalp", ["1m", "3m"], ["EMA9/21", "VWAP", "Range"], "sim"),
    ("intra", ["5m", "15m"], ["EMA20/50", "RSI", "ATR"], "sim"),
    ("swing", ["1h", "4h"], ["EMA50/200", "MACD", "ADX"], "sim"),
    ("macro", ["1h", "1d"], ["MacroScore", "News", "ATR"], "sim"),
    ("quant", ["15m", "1h"], ["ZScore", "VWAP", "ATR"], "sim"),
]


def _random_name(category: str, idx: int) -> str:
    return f"{category.upper()}_{idx:04d}"


def build_profiles(total: int) -> List[StrategyProfile]:
    cfg = load_cup_config()
    profiles: List[StrategyProfile] = []
    iterator = itertools.count(1)
    while len(profiles) < total:
        for category, tfs, indicators, engine in CATEGORIES:
            idx = next(iterator)
            tf = random.choice(tfs)
            stats = StrategyStats(balance=cfg.starting_balance, goal=cfg.initial_goal)
            profile = StrategyProfile(
                id=f"{category}_{idx}",
                name=_random_name(category, idx),
                category=category,
                timeframe=tf,
                indicators=indicators,
                mode="training",
                engine=engine,
                stats=stats,
                notes=f"Auto generado para {category}"
            )
            profiles.append(profile)
            if len(profiles) >= total:
                break
        if len(profiles) >= total:
            break
    return profiles


def main(total: int, output: Path | None = None) -> None:
    registry = ArenaRegistry(output)
    registry.extend(build_profiles(total))
    registry.save()
    print(f"Arena generada con {len(registry.all())} estrategias en {registry.path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera estrategias masivas")
    parser.add_argument("--total", type=int, default=5000, help="Número de estrategias a crear")
    parser.add_argument("--output", type=Path, default=None, help="Ruta opcional del registry")
    args = parser.parse_args()
    main(args.total, args.output)
