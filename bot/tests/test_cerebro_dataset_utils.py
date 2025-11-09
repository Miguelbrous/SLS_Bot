from bot.cerebro import dataset_utils


def test_summarize_rows_counts():
    rows = [
        {"pnl": 10, "symbol": "BTCUSDT", "decision": "LONG", "timeframe": "15m"},
        {"pnl": -5, "symbol": "BTCUSDT", "decision": "SHORT", "timeframe": "15m"},
        {"pnl": 0, "symbol": "ETHUSDT", "decision": "LONG", "timeframe": "1h"},
    ]
    summary = dataset_utils.summarize_rows(rows)
    assert summary["total"] == 3
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert summary["symbols"]["BTCUSDT"] == 2
    assert summary["symbols"]["ETHUSDT"] == 1
    assert summary["long_rate"] == 2 / 3
    assert summary["short_rate"] == 1 / 3
    assert 2 / 3 == summary["dominant_symbol_share"]
