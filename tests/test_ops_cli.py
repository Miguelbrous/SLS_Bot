from __future__ import annotations

from typing import List

import pytest

from scripts import ops


@pytest.fixture()
def stub_run(monkeypatch):
    calls: List[List[str]] = []

    def _fake_run(cmd, **kwargs):
        calls.append(cmd)

    monkeypatch.setattr(ops, "_run", _fake_run)
    monkeypatch.setattr(ops, "_python_exec", lambda: "python")
    return calls


def test_infra_command_invokes_infra_check(stub_run):
    parser = ops.build_parser()
    args = parser.parse_args(["infra", "--env-file", ".env.local", "--ensure-dirs"])
    args.func(args)
    assert stub_run == [
        ["python", str(ops.INFRA_CHECK), "--env-file", ".env.local", "--ensure-dirs"],
    ]


def test_cerebro_dataset_command_builds_expected_args(stub_run):
    parser = ops.build_parser()
    args = parser.parse_args(
        ["cerebro", "dataset", "--mode", "real", "--rows", "250", "--bias", "0.25", "--overwrite"]
    )
    args.func(args)
    assert stub_run[-1] == [
        "python",
        str(ops.GENERATE_DATASET),
        "--mode",
        "real",
        "--rows",
        "250",
        "--bias",
        "0.25",
        "--overwrite",
    ]


def test_cerebro_promote_command_accepts_min_value(stub_run):
    parser = ops.build_parser()
    args = parser.parse_args(
        ["cerebro", "promote", "--mode", "real", "--metric", "win_rate", "--min-value", "0.7"]
    )
    args.func(args)
    assert stub_run[-1] == [
        "python",
        str(ops.PROMOTE_MODEL),
        "--mode",
        "real",
        "--metric",
        "win_rate",
        "--min-value",
        "0.7",
    ]
