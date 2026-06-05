from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from quant_trader.factors import compute_factor_scores, select_top_scores
from quant_trader.market_data import MarketSeries, sample_history
from quant_trader.simulation import simulate_portfolio
from quant_trader.storage import SQLiteBarStore


class InstitutionalFrameworkTests(unittest.TestCase):
    def test_sqlite_bar_store_round_trips_bars(self) -> None:
        bars = sample_history("AAPL", points=20)
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteBarStore(Path(tmp) / "bars.sqlite")
            saved = store.save_bars(
                "AAPL",
                bars,
                source="sample",
                exchange_timezone="America/New_York",
                data_range="1mo",
                interval="1d",
            )
            loaded = store.load_bars("AAPL", data_range="1mo", interval="1d")

        self.assertEqual(saved, 20)
        self.assertEqual(len(loaded), 20)
        self.assertEqual(loaded[-1].close, bars[-1].close)

    def test_factor_scores_select_leaders(self) -> None:
        bars_by_symbol = {
            "AAPL": sample_history("AAPL", points=180),
            "MSFT": sample_history("MSFT", points=180),
            "NVDA": sample_history("NVDA", points=180),
        }

        scores = compute_factor_scores(bars_by_symbol)
        leaders = select_top_scores(scores, top_n=2)

        self.assertEqual(len(scores), 3)
        self.assertLessEqual(len(leaders), 2)
        self.assertTrue(all(score.total_score > 0 for score in leaders))

    def test_multi_factor_strategy_returns_report(self) -> None:
        market = {
            "AAPL": MarketSeries("AAPL", "sample", sample_history("AAPL", points=180)),
            "MSFT": MarketSeries("MSFT", "sample", sample_history("MSFT", points=180)),
            "NVDA": MarketSeries("NVDA", "sample", sample_history("NVDA", points=180)),
        }

        result = simulate_portfolio(
            market,
            initial_cash=100_000,
            strategy_name="multi_factor_top",
            top_n=2,
            data_range="1y",
            interval="1d",
        )

        self.assertEqual(result["parameters"]["strategy"]["key"], "multi_factor_top")
        self.assertIn("report", result["portfolio"])
        self.assertIn("factor_scores", result["symbols"]["AAPL"])


if __name__ == "__main__":
    unittest.main()
