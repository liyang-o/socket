from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

from quant_trader.market_calendar import (
    market_holiday_reason,
    market_session_info,
    to_market_time,
)
from quant_trader.market_data import sample_intraday


class MarketCalendarTests(unittest.TestCase):
    def test_market_session_open_uses_new_york_time(self) -> None:
        # 2026-06-04 14:00 UTC is 10:00 ET during US daylight time.
        info = market_session_info(datetime(2026, 6, 4, 14, 0, tzinfo=timezone.utc))

        self.assertTrue(info.is_trading_day)
        self.assertTrue(info.is_open)
        self.assertEqual(info.status, "open")
        self.assertEqual(info.session_date, "2026-06-04")
        self.assertIn("09:30 ET", info.open_time_et or "")

    def test_market_holiday_rules_include_major_exchange_closures(self) -> None:
        self.assertEqual(market_holiday_reason(date(2026, 6, 19)), "Juneteenth")
        self.assertEqual(market_holiday_reason(date(2026, 4, 3)), "Good Friday")
        self.assertEqual(market_holiday_reason(date(2026, 6, 6)), "Weekend")

    def test_sample_intraday_uses_regular_session_times(self) -> None:
        bars = sample_intraday(
            "AAPL",
            points=390,
            now=datetime(2026, 6, 4, 18, 0, tzinfo=timezone.utc),
        )

        first = to_market_time(bars[0].time)
        last = to_market_time(bars[-1].time)
        self.assertEqual((first.hour, first.minute), (9, 30))
        self.assertEqual((last.hour, last.minute), (14, 0))
        self.assertTrue(all("ET" in bar.time_et for bar in bars))


if __name__ == "__main__":
    unittest.main()
