from pathlib import Path

from scripts.tools import autopilot_summary


def test_autopilot_summary_outputs(tmp_path: Path):
    dataset = Path("sample_data/cerebro_experience_sample.jsonl")
    runs = [Path("sample_data/arena_runs_sample.jsonl")]
    args = autopilot_summary.parse_args(
        [
            "--dataset",
            str(dataset),
            "--runs",
            str(runs[0]),
            "--min-trades",
            "50",
            "--max-drawdown",
            "5",
            "--output-json",
            str(tmp_path / "summary.json"),
        ]
    )
    summary = autopilot_summary.autopilot_summary(args)
    assert summary["dataset"]["summary"]["total"] >= 1
    assert summary["arena"]["accepted"]
    assert summary["arena"]["accepted"][0]["name"] == "strategy_alpha"
