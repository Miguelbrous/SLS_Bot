from pathlib import Path
import json

from scripts.tools import arena_rank


def test_rank_filters_and_scores(tmp_path: Path):
    data = [
        {
            "name": "good",
            "stats": {
                "pnl": 1200,
                "max_drawdown": 3.0,
                "gross_profit": 4000,
                "gross_loss": -1800,
                "trades": 120,
                "win_rate": 0.58,
                "returns_avg": 0.03,
                "returns_std": 0.02,
            },
        },
        {
            "name": "bad-drawdown",
            "stats": {
                "pnl": 900,
                "max_drawdown": 8.0,
                "gross_profit": 2000,
                "gross_loss": -1500,
                "trades": 140,
                "win_rate": 0.52,
                "returns_avg": 0.02,
                "returns_std": 0.03,
            },
        },
    ]
    file = tmp_path / "runs.jsonl"
    file.write_text("\n".join(json.dumps(item) for item in data), encoding="utf-8")

    args = arena_rank.parse_args([str(file), "--json"])
    result = arena_rank.rank_candidates([file], args)

    assert result["accepted"] and result["accepted"][0]["name"] == "good"
    assert result["rejected"][0]["name"] == "bad-drawdown"
