from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from quant_trader.static_site import generate_static_site


class StaticSiteTests(unittest.TestCase):
    def test_generate_static_site_writes_pages_assets_and_snapshot(self) -> None:
        previous = os.environ.get("QUANT_TRADER_OFFLINE")
        os.environ["QUANT_TRADER_OFFLINE"] = "1"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                output = generate_static_site(
                    Path(tmp) / "public",
                    symbols="AAPL,MSFT",
                    initial_cash=20_000,
                    fast_window=4,
                    slow_window=9,
                    strategy_name="hybrid_reversion",
                )

                snapshot_path = output / "data" / "latest.json"
                self.assertTrue((output / "index.html").is_file())
                self.assertTrue((output / ".nojekyll").is_file())
                self.assertTrue(snapshot_path.is_file())

                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
                self.assertEqual(snapshot["metadata"]["mode"], "github_pages_snapshot")
                self.assertEqual(snapshot["metadata"]["symbols"], ["AAPL", "MSFT"])
                self.assertEqual(snapshot["parameters"]["strategy"]["key"], "hybrid_reversion")
                self.assertEqual(snapshot["parameters"]["fast_window"], 4)
                self.assertIn("portfolio", snapshot)
        finally:
            if previous is None:
                os.environ.pop("QUANT_TRADER_OFFLINE", None)
            else:
                os.environ["QUANT_TRADER_OFFLINE"] = previous


if __name__ == "__main__":
    unittest.main()
