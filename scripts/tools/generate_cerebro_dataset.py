#!/usr/bin/env python3
"""
Generador rápido de experiencias sintéticas para el Cerebro IA.

Permite poblar logs/<mode>/cerebro_experience.jsonl con datos plausibles para
ejercitar `cerebro.train` y validar el pipeline de auto-entrenamiento sin tocar
cuentas reales.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Dict, Tuple

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODE = "test"
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_TIMEFRAME = "15m"


def _paths_for_mode(mode: str) -> Tuple[Path, Path]:
    logs_dir = ROOT / "logs" / mode
    dataset = logs_dir / "cerebro_experience.jsonl"
    return logs_dir, dataset


def _random_experience(rng: random.Random, bullish_bias: float) -> Dict:
    confidence = rng.uniform(0.35, 0.9)
    ml_score = max(0.05, min(0.95, confidence + rng.uniform(-0.15, 0.15)))
    news_sentiment = rng.uniform(-0.6, 0.6)
    session_guard_state = rng.choices(
        population=["normal", "pre_open", "news_wait", "news_ready"],
        weights=[0.7, 0.1, 0.1, 0.1],
        k=1,
    )[0]
    guard_multiplier = 0.7 if session_guard_state in {"pre_open", "news_wait"} else rng.uniform(0.85, 1.15)
    memory_win_rate = rng.uniform(0.35, 0.7)
    leverage = rng.choice([5, 8, 10, 12, 15])
    risk_pct = rng.uniform(0.4, 1.2)

    score = (
        0.5 * confidence
        + 0.3 * ml_score
        + 0.2 * (0.5 + 0.5 * news_sentiment)
        + 0.1 * memory_win_rate
        - 0.15 * (1.0 - guard_multiplier)
    )
    score += bullish_bias
    pnl = rng.gauss(mu=score * 8.0 - 3.0, sigma=2.5)
    if session_guard_state in {"pre_open", "news_wait"}:
        pnl = min(pnl, rng.uniform(-6.0, 1.0))

    features = {
        "confidence": round(confidence, 4),
        "risk_pct": round(risk_pct, 4),
        "leverage": float(leverage),
        "news_sentiment": round(news_sentiment, 4),
        "session_guard_risk_multiplier": round(guard_multiplier, 4),
        "memory_win_rate": round(memory_win_rate, 4),
        "ml_score": round(ml_score, 4),
        "session_guard_penalty": 1.0 if session_guard_state in {"pre_open", "news_wait"} else 0.0,
        "session_guard_state": session_guard_state,
    }

    return {
        "symbol": DEFAULT_SYMBOL,
        "timeframe": DEFAULT_TIMEFRAME,
        "decision": "LONG" if confidence >= 0.5 else "SHORT",
        "pnl": round(pnl, 4),
        "features": features,
    }


def generate_dataset(mode: str, rows: int, overwrite: bool, bullish_bias: float) -> Path:
    rng = random.Random(1337)
    logs_dir, dataset_path = _paths_for_mode(mode)
    logs_dir.mkdir(parents=True, exist_ok=True)
    if dataset_path.exists() and not overwrite:
        raise FileExistsError(f"El dataset {dataset_path} ya existe. Usa --overwrite para reemplazarlo.")

    positives_target = max(1, int(rows * 0.55))
    negatives_target = rows - positives_target
    positives = negatives = 0
    buffer = []

    while len(buffer) < rows:
        exp = _random_experience(rng, bullish_bias=bullish_bias)
        if exp["pnl"] > 0 and positives < positives_target:
            positives += 1
            buffer.append(exp)
        elif exp["pnl"] <= 0 and negatives < negatives_target:
            negatives += 1
            buffer.append(exp)

    rng.shuffle(buffer)
    with dataset_path.open("w", encoding="utf-8") as fh:
        for item in buffer:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    return dataset_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera un dataset sintético compatible con cerebro.train.")
    parser.add_argument("--mode", type=str, default=DEFAULT_MODE, help="Modo objetivo (test, real, etc.).")
    parser.add_argument("--rows", type=int, default=200, help="Número de experiencias a generar (>=50).")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Reemplaza el dataset existente en logs/<mode>/cerebro_experience.jsonl.",
    )
    parser.add_argument(
        "--bias",
        type=float,
        default=0.0,
        help="Sesgo adicional (positivo favorece pnl>0, negativo más pérdidas).",
    )
    args = parser.parse_args()
    if args.rows < 50:
        raise SystemExit("Se requieren al menos 50 filas para entrenar el modelo.")
    dataset_path = generate_dataset(args.mode.lower(), args.rows, args.overwrite, args.bias)
    print(json.dumps({"ok": True, "dataset": str(dataset_path), "rows": args.rows}, ensure_ascii=False))


if __name__ == "__main__":
    main()
