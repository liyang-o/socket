from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from quant_trader.market_data import Bar, MarketSeries, parse_symbols, sample_intraday
from quant_trader.simulation import simulate_portfolio
from quant_trader.strategy import simple_moving_average, sma_crossover_signals


class StrategyTests(unittest.TestCase):
    def test_simple_moving_average(self) -> None:
        self.assertEqual(
            simple_moving_average([1, 2, 3, 4, 5], 3),
            [None, None, 2.0, 3.0, 4.0],
        )

    def test_sma_crossover_signals_emit_buy_and_sell(self) -> None:
        closes = [10, 10, 10, 10, 12, 14, 16, 18, 16, 14, 12, 10, 8]
        bars = _bars_from_closes(closes)

        points = sma_crossover_signals(bars, fast_window=2, slow_window=4)
        signals = [point.signal for point in points]

        self.assertIn("buy", signals)
        self.assertIn("sell", signals)

    def test_parse_symbols_normalizes_and_deduplicates(self) -> None:
        self.assertEqual(parse_symbols(" aapl,MSFT,aapl "), ["AAPL", "MSFT"])


class SimulationTests(unittest.TestCase):
    def test_simulate_portfolio_returns_metrics(self) -> None:
        series = MarketSeries("AAPL", "sample", sample_intraday("AAPL", points=80))

        result = simulate_portfolio(
            {"AAPL": series},
            initial_cash=10_000,
            fast_window=4,
            slow_window=9,
            commission_rate=0.001,
        )

        self.assertIn("portfolio", result)
        self.assertIn("AAPL", result["symbols"])
        self.assertGreater(result["portfolio"]["equity"], 0)
        self.assertEqual(result["parameters"]["fast_window"], 4)


def _bars_from_closes(closes: list[float]) -> list[Bar]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars: list[Bar] = []
    for index, close in enumerate(closes):
        bars.append(
            Bar(
                time=(start + timedelta(minutes=index)).isoformat(),
                open=close,
                high=close + 0.5,
                low=close - 0.5,
                close=close,
                volume=1000,
            )
        )
    return bars


if __name__ == "__main__":
    unittest.main()
