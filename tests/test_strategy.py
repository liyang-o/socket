from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from quant_trader.market_data import Bar, MarketSeries, normalize_symbol, parse_symbols, sample_intraday
from quant_trader.simulation import simulate_portfolio
from quant_trader.indicators import bollinger_bands, relative_strength_index, simple_moving_average
from quant_trader.strategy import available_strategies, generate_signals, sma_crossover_signals
from quant_trader.universes import universe_symbols


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

    def test_available_strategies_include_new_signal_families(self) -> None:
        keys = {strategy["key"] for strategy in available_strategies()}

        self.assertIn("rsi_reversion", keys)
        self.assertIn("bollinger_reversion", keys)
        self.assertIn("hybrid_reversion", keys)
        self.assertIn("momentum_rotation", keys)
        self.assertIn("dual_momentum", keys)
        self.assertIn("trend_pullback", keys)
        self.assertIn("regime_adaptive", keys)

    def test_rsi_and_bollinger_indicators_emit_values(self) -> None:
        closes = [10, 9, 8, 9, 10, 11, 12, 11, 10, 9, 8, 9, 10, 11, 12, 13]

        rsi = relative_strength_index(closes, 5)
        lower, middle, upper = bollinger_bands(closes, 5, 2)

        self.assertIsNotNone(rsi[-1])
        self.assertIsNotNone(lower[-1])
        self.assertLess(lower[-1], middle[-1])
        self.assertLess(middle[-1], upper[-1])

    def test_generate_signals_adds_strategy_specific_fields(self) -> None:
        bars = _bars_from_closes(
            [10, 9, 8, 9, 10, 11, 12, 11, 10, 9, 8, 9, 10, 11, 12, 13] * 2
        )

        rsi_points = generate_signals(bars, "rsi_reversion")
        bollinger_points = generate_signals(bars, "bollinger_reversion")

        self.assertTrue(any(point.rsi is not None for point in rsi_points))
        self.assertTrue(any(point.bb_lower is not None for point in bollinger_points))

    def test_regime_strategy_emits_regime_labels(self) -> None:
        bars = _bars_from_closes([10 + index * 0.1 for index in range(90)])

        points = generate_signals(bars, "regime_adaptive")

        self.assertTrue(any(point.regime is not None for point in points))

    def test_parse_symbols_normalizes_and_deduplicates(self) -> None:
        self.assertEqual(parse_symbols(" aapl,MSFT,aapl "), ["AAPL", "MSFT"])

    def test_a_share_symbol_normalization(self) -> None:
        self.assertEqual(normalize_symbol("600519"), "600519.SS")
        self.assertEqual(normalize_symbol("sz000001"), "000001.SZ")

    def test_universe_presets_include_us_top_100_and_a_shares(self) -> None:
        self.assertEqual(len(universe_symbols("us_top_100")), 100)
        self.assertIn("600519.SS", universe_symbols("a_share_core"))


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

    def test_simulate_portfolio_supports_momentum_rotation(self) -> None:
        market = {
            "AAPL": MarketSeries("AAPL", "sample", sample_intraday("AAPL", points=120)),
            "MSFT": MarketSeries("MSFT", "sample", sample_intraday("MSFT", points=120)),
        }

        result = simulate_portfolio(
            market,
            initial_cash=10_000,
            strategy_name="momentum_rotation",
            momentum_window=20,
        )

        self.assertEqual(result["parameters"]["strategy"]["key"], "momentum_rotation")
        self.assertIn("available_strategies", result["parameters"])
        self.assertGreater(result["portfolio"]["equity"], 0)

    def test_simulate_portfolio_records_data_range_and_interval(self) -> None:
        series = MarketSeries("AAPL", "sample", sample_intraday("AAPL", points=80))

        result = simulate_portfolio(
            {"AAPL": series},
            initial_cash=10_000,
            data_range="1y",
            interval="1d",
        )

        self.assertEqual(result["parameters"]["range"], "1y")
        self.assertEqual(result["parameters"]["interval"], "1d")


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
