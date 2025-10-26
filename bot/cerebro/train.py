from __future__ import annotations

import argparse
import json
import math
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

ROOT_DIR = Path(__file__).resolve().parents[2]


def _default_mode() -> str:
    return (os.getenv("SLS_CEREBRO_MODE") or os.getenv("SLSBOT_MODE") or "test").lower()


def _dataset_for_mode(mode: str) -> Path:
    return Path(ROOT_DIR / "logs" / mode / "cerebro_experience.jsonl")


def _output_for_mode(mode: str) -> Path:
    return Path(ROOT_DIR / "models" / "cerebro" / mode)

FEATURES = [
    "confidence",
    "risk_pct",
    "leverage",
    "news_sentiment",
    "session_guard_risk_multiplier",
    "memory_win_rate",
    "ml_score",
    "session_guard_penalty",
]


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


def preprocess(rows: Sequence[dict], stats: Tuple[List[float], List[float]] | None = None) -> Tuple[List[List[float]], List[int], List[float], List[float]]:
    vectors: List[List[float]] = []
    labels: List[int] = []
    for item in rows:
        pnl = float(item.get("pnl") or 0.0)
        label = 1 if pnl > 0 else 0
        features = item.get("features") or {}
        session_state = (features.get("session_guard_state") or "").lower()
        vector: List[float] = []
        for name in FEATURES:
            if name == "session_guard_penalty":
                val = 1.0 if session_state in {"pre_open", "news_wait"} else 0.0
            else:
                val = features.get(name)
                if val is None:
                    defaults = {
                        "confidence": 0.5,
                        "risk_pct": 1.0,
                        "leverage": 10.0,
                        "news_sentiment": 0.0,
                        "session_guard_risk_multiplier": 1.0,
                        "memory_win_rate": 0.5,
                        "ml_score": 0.5,
                    }
                    val = defaults.get(name, 0.0)
            vector.append(float(val))
        vectors.append(vector)
        labels.append(label)

    if stats:
        means, stds = stats
    else:
        means = []
        stds = []
        for idx in range(len(FEATURES)):
            column = [vec[idx] for vec in vectors]
            mean = sum(column) / len(column)
            variance = sum((val - mean) ** 2 for val in column) / max(1, len(column) - 1)
            std = math.sqrt(variance) or 1.0
            means.append(mean)
            stds.append(std)
    for idx in range(len(FEATURES)):
        mean = means[idx]
        std = stds[idx] or 1.0
        for row in vectors:
            row[idx] = (row[idx] - mean) / std

    return vectors, labels, means, stds


def train_model(x: List[List[float]], y: List[int], epochs: int = 400, lr: float = 0.05) -> Tuple[List[float], float]:
    weights = [0.0 for _ in FEATURES]
    bias = 0.0
    for epoch in range(epochs):
        grad_w = [0.0 for _ in FEATURES]
        grad_b = 0.0
        for x_vec, label in zip(x, y):
            z = bias + sum(w * x for w, x in zip(weights, x_vec))
            pred = 1.0 / (1.0 + math.exp(-z))
            error = pred - label
            for i in range(len(weights)):
                grad_w[i] += error * x_vec[i]
            grad_b += error
        n = len(x)
        for i in range(len(weights)):
            weights[i] -= lr * (grad_w[i] / n)
        bias -= lr * (grad_b / n)
    return weights, bias


def evaluate(weights: List[float], bias: float, x: List[List[float]], y: List[int]) -> Tuple[float, float, float]:
    preds: List[float] = []
    correct = 0
    wins = sum(y)
    for x_vec, label in zip(x, y):
        z = bias + sum(w * x for w, x in zip(weights, x_vec))
        prob = 1.0 / (1.0 + math.exp(-z))
        preds.append(prob)
        correct += 1 if (prob >= 0.5 and label == 1) or (prob < 0.5 and label == 0) else 0
    accuracy = correct / max(1, len(x))
    win_rate = wins / max(1, len(y))
    auc = _compute_auc(preds, y)
    return accuracy, win_rate, auc


def _compute_auc(preds: Sequence[float], labels: Sequence[int]) -> float:
    paired = sorted(zip(preds, labels), key=lambda x: x[0])
    pos = sum(labels)
    neg = len(labels) - pos
    if pos == 0 or neg == 0:
        return 0.5
    rank_sum = 0.0
    for idx, (_, label) in enumerate(paired, 1):
        if label == 1:
            rank_sum += idx
    auc = (rank_sum - pos * (pos + 1) / 2) / (pos * neg)
    return auc


def save_artifact(output_dir: Path, mode: str, weights: List[float], bias: float, means: List[float], stds: List[float], metrics: Dict[str, float]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    artifact = {
        "version": timestamp,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "mode": mode,
        "bias": bias,
        "features": [
            {
                "name": name,
                "weight": weights[idx],
                "mean": means[idx],
                "std": stds[idx],
                "default": 0.0,
            }
            for idx, name in enumerate(FEATURES)
        ],
        "metrics": metrics,
    }
    artifact_path = output_dir / f"model_{timestamp}.json"
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_path = output_dir / "latest_model.json"
    latest_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    return artifact_path


def maybe_promote(artifact_path: Path, metrics: Dict[str, float], min_auc: float, min_win_rate: float) -> bool:
    output_dir = artifact_path.parent
    meta_path = output_dir / "meta.json"
    prev_metrics = {}
    if meta_path.exists():
        try:
            prev_metrics = json.loads(meta_path.read_text(encoding="utf-8")).get("metrics", {})
        except Exception:
            prev_metrics = {}
    auc = metrics.get("auc") or 0.0
    win_rate = metrics.get("win_rate") or 0.0
    prev_auc = prev_metrics.get("auc")
    should_promote = auc >= min_auc and win_rate >= min_win_rate and (prev_auc is None or auc >= prev_auc)
    if not should_promote:
        return False
    active_path = output_dir / "active_model.json"
    artifact_data = artifact_path.read_text(encoding="utf-8")
    active_path.write_text(artifact_data, encoding="utf-8")
    version = json.loads(artifact_data).get("version")
    meta_path.write_text(json.dumps({"metrics": metrics, "version": version}, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Entrena el modelo ligero del Cerebro IA.")
    parser.add_argument("--mode", type=str, default=None, help="Modo/profil (test, real, etc.). Por defecto usa SLSBOT_MODE o 'test'.")
    parser.add_argument("--dataset", type=Path, default=None, help="Ruta del jsonl con experiencias (por defecto logs/<mode>/cerebro_experience.jsonl).")
    parser.add_argument("--output-dir", type=Path, default=None, help="Carpeta donde guardar artefactos (por defecto models/cerebro/<mode>).")
    parser.add_argument("--epochs", type=int, default=400)
    parser.add_argument("--lr", type=float, default=0.05)
    parser.add_argument("--min-auc", type=float, default=0.52)
    parser.add_argument("--min-win-rate", type=float, default=0.52)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    return parser


def main() -> None:
    parser = build_argparser()
    args = parser.parse_args()
    mode = (args.mode or _default_mode()).lower()
    dataset_path = args.dataset or _dataset_for_mode(mode)
    output_dir = args.output_dir or _output_for_mode(mode)
    rows = load_rows(dataset_path)
    if len(rows) < 50:
        raise SystemExit(f"Se necesitan al menos 50 experiencias, solo hay {len(rows)}")
    random.Random(42).shuffle(rows)
    split_idx = max(1, int(len(rows) * min(max(args.train_ratio, 0.1), 0.9)))
    train_rows = rows[:split_idx]
    test_rows = rows[split_idx:]
    train_x, train_y, means, stds = preprocess(train_rows)
    weights, bias = train_model(train_x, train_y, epochs=args.epochs, lr=args.lr)
    test_x, test_y, _, _ = preprocess(test_rows, stats=(means, stds))
    accuracy, win_rate, auc = evaluate(weights, bias, test_x, test_y)
    metrics = {
        "accuracy": round(accuracy, 4),
        "win_rate": round(win_rate, 4),
        "auc": round(auc, 4),
        "samples_train": len(train_rows),
        "samples_test": len(test_rows),
    }
    artifact_path = save_artifact(output_dir, mode, weights, bias, means, stds, metrics)
    promoted = maybe_promote(artifact_path, metrics, args.min_auc, args.min_win_rate)
    status = "PROMOVIDO" if promoted else "SOLO_ENTRENADO"
    print(
        json.dumps(
            {"status": status, "artifact": str(artifact_path), "metrics": metrics, "mode": mode},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
