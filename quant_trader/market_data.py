"""Market data loading for the paper trading demo.

The live source uses Yahoo Finance's public chart endpoint. It is suitable for
education and paper trading demos, not for production order routing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import math
import os
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .market_calendar import (
    MARKET_TZ_NAME,
    MARKET_TZ,
    filter_regular_session_bars,
    market_session_info,
    market_time_label,
    previous_trading_day,
    session_bounds,
    timezone_time_label,
    to_utc_iso,
)


YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
DEFAULT_USER_AGENT = "quant-paper-trader/0.1 (+https://github.com)"


@dataclass(frozen=True)
class Bar:
    """A single OHLCV market bar."""

    time: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    time_et: str = ""
    time_local: str = ""
    timezone: str = MARKET_TZ_NAME

    def to_dict(self) -> dict[str, float | int | str]:
        payload = asdict(self)
        payload["time_et"] = self.time_et or market_time_label(self.time)
        payload["time_local"] = self.time_local or timezone_time_label(self.time, self.timezone)
        return payload


@dataclass(frozen=True)
class MarketSeries:
    """Bars plus metadata about where they came from."""

    symbol: str
    source: str
    bars: list[Bar]
    exchange_timezone: str = MARKET_TZ_NAME
    data_range: str = ""
    interval: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "source": self.source,
            "exchange_timezone": self.exchange_timezone,
            "data_range": self.data_range,
            "interval": self.interval,
            "bars": [bar.to_dict() for bar in self.bars],
        }


def normalize_symbol(symbol: str) -> str:
    """Return a safe uppercase ticker symbol."""

    cleaned = "".join(ch for ch in symbol.upper().strip() if ch.isalnum() or ch in ".=-")
    if not cleaned:
        raise ValueError("symbol cannot be empty")
    return cleaned


def parse_symbols(raw_symbols: str | Iterable[str]) -> list[str]:
    """Parse and de-duplicate symbols while preserving order."""

    if isinstance(raw_symbols, str):
        candidates = raw_symbols.split(",")
    else:
        candidates = raw_symbols

    symbols: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        symbol = normalize_symbol(candidate)
        if symbol not in seen:
            symbols.append(symbol)
            seen.add(symbol)
    if not symbols:
        raise ValueError("at least one symbol is required")
    return symbols


def fetch_intraday(symbol: str, data_range: str = "6mo", interval: str = "1d") -> MarketSeries:
    """Fetch recent bars for a symbol, falling back to generated sample data.

    Set ``QUANT_TRADER_OFFLINE=1`` to force deterministic sample data. This
    keeps the demo usable in CI, classrooms, and restricted networks.
    """

    normalized = normalize_symbol(symbol)
    if os.getenv("QUANT_TRADER_OFFLINE") == "1":
        return MarketSeries(
            normalized,
            "sample",
            sample_bars(normalized, data_range=data_range, interval=interval),
            data_range=data_range,
            interval=interval,
        )

    try:
        bars, exchange_timezone = _fetch_yahoo_chart(normalized, data_range, interval)
        if _should_filter_regular_session(interval, exchange_timezone):
            bars = filter_regular_session_bars(bars)
    except (HTTPError, URLError, TimeoutError, KeyError, IndexError, TypeError, ValueError):
        bars = []
        exchange_timezone = MARKET_TZ_NAME

    if len(bars) < 30:
        return MarketSeries(
            normalized,
            "sample",
            sample_bars(normalized, data_range=data_range, interval=interval),
            data_range=data_range,
            interval=interval,
        )
    return MarketSeries(normalized, "yahoo", bars, exchange_timezone, data_range, interval)


def _fetch_yahoo_chart(symbol: str, data_range: str, interval: str) -> tuple[list[Bar], str]:
    query = urlencode(
        {
            "range": data_range,
            "interval": interval,
            "includePrePost": "false",
            "events": "div,splits",
        }
    )
    url = f"{YAHOO_CHART_URL.format(symbol=symbol)}?{query}"
    request = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})

    with urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))

    result = payload["chart"]["result"][0]
    meta = result.get("meta", {})
    exchange_timezone = meta.get("exchangeTimezoneName") or MARKET_TZ_NAME
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]

    bars: list[Bar] = []
    for index, epoch in enumerate(timestamps):
        close = _safe_float(quote["close"][index])
        open_ = _safe_float(quote["open"][index])
        high = _safe_float(quote["high"][index])
        low = _safe_float(quote["low"][index])
        if close is None:
            continue

        open_ = close if open_ is None else open_
        high = close if high is None else high
        low = close if low is None else low
        volume = quote.get("volume", [0] * len(timestamps))[index] or 0
        timestamp = datetime.fromtimestamp(epoch, tz=timezone.utc)

        bars.append(
            Bar(
                time=timestamp.isoformat(),
                open=round(open_, 4),
                high=round(high, 4),
                low=round(low, 4),
                close=round(close, 4),
                volume=int(volume),
                time_et=market_time_label(timestamp),
                time_local=timezone_time_label(timestamp, exchange_timezone),
                timezone=exchange_timezone,
            )
        )
    return bars, exchange_timezone


def sample_bars(symbol: str, data_range: str = "6mo", interval: str = "1d") -> list[Bar]:
    """Generate fallback bars that match the requested interval style."""

    if _is_intraday_interval(interval):
        return sample_intraday(symbol)
    return sample_history(symbol, points=_range_to_daily_points(data_range))


def sample_intraday(symbol: str, points: int = 391, now: datetime | None = None) -> list[Bar]:
    """Generate realistic-looking intraday data when live data is unavailable."""

    seed = sum(ord(ch) for ch in symbol)
    base_price = 70 + seed % 180
    trend = ((seed % 9) - 4) / 900
    start, end = _sample_session_window(now)
    total_minutes = int((end - start).total_seconds() // 60) + 1
    point_count = max(1, min(points, total_minutes))
    start = end - timedelta(minutes=point_count - 1)

    bars: list[Bar] = []
    previous_close = float(base_price)
    for index in range(point_count):
        current_time = start + timedelta(minutes=index)
        progress = index / max(point_count - 1, 1)
        day_trend = trend * progress
        wave = math.sin(index / 8 + seed) * 0.012
        pulse = math.sin(index / 21 + seed / 7) * 0.006
        close = max(1.0, base_price * (1 + day_trend + wave + pulse))
        high = max(previous_close, close) * (1 + 0.0025)
        low = min(previous_close, close) * (1 - 0.0025)
        volume = 50_000 + ((seed * 97 + index * 7919) % 750_000)

        bars.append(
            Bar(
                time=to_utc_iso(current_time),
                open=round(previous_close, 4),
                high=round(high, 4),
                low=round(low, 4),
                close=round(close, 4),
                volume=volume,
                time_et=market_time_label(current_time),
                time_local=timezone_time_label(current_time, MARKET_TZ_NAME),
                timezone=MARKET_TZ_NAME,
            )
        )
        previous_close = close
    return bars


def sample_history(symbol: str, points: int = 252, now: datetime | None = None) -> list[Bar]:
    """Generate daily historical bars on recent US trading days."""

    seed = sum(ord(ch) for ch in symbol)
    base_price = 70 + seed % 180
    reference = now or datetime.now(MARKET_TZ)
    current_day = previous_trading_day(reference.astimezone(MARKET_TZ).date())
    trading_days = []
    while len(trading_days) < points:
        trading_days.append(current_day)
        current_day = previous_trading_day(current_day - timedelta(days=1))
    trading_days.reverse()

    bars: list[Bar] = []
    previous_close = float(base_price)
    for index, trading_day in enumerate(trading_days):
        progress = index / max(points - 1, 1)
        trend = ((seed % 11) - 5) / 1200
        cycle = math.sin(index / 17 + seed) * 0.018
        slow_cycle = math.sin(index / 53 + seed / 5) * 0.012
        close = max(1.0, base_price * (1 + trend * index + cycle + slow_cycle + progress * 0.015))
        high = max(previous_close, close) * (1 + 0.006)
        low = min(previous_close, close) * (1 - 0.006)
        volume = 500_000 + ((seed * 193 + index * 104729) % 6_000_000)
        bounds = session_bounds(trading_day)
        if bounds is None:
            continue
        timestamp = bounds[1]

        bars.append(
            Bar(
                time=to_utc_iso(timestamp),
                open=round(previous_close, 4),
                high=round(high, 4),
                low=round(low, 4),
                close=round(close, 4),
                volume=volume,
                time_et=market_time_label(timestamp),
                time_local=timezone_time_label(timestamp, MARKET_TZ_NAME),
                timezone=MARKET_TZ_NAME,
            )
        )
        previous_close = close
    return bars


def _sample_session_window(now: datetime | None) -> tuple[datetime, datetime]:
    reference = now or datetime.now(timezone.utc)
    info = market_session_info(reference)
    reference_et = reference.astimezone(MARKET_TZ).replace(second=0, microsecond=0)

    if info.is_trading_day and info.status == "open":
        bounds = session_bounds(reference_et.date())
        if bounds is None:
            raise ValueError("trading session unexpectedly unavailable")
        open_dt, close_dt = bounds
        return open_dt, min(reference_et, close_dt)

    if info.is_trading_day and info.status == "after_hours":
        session_date = reference_et.date()
    else:
        session_date = previous_trading_day(reference_et.date() - timedelta(days=1))

    bounds = session_bounds(session_date)
    if bounds is None:
        raise ValueError("trading session unexpectedly unavailable")
    return bounds


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _is_intraday_interval(interval: str) -> bool:
    normalized = interval.lower()
    return normalized.endswith("m") or normalized.endswith("h")


def _should_filter_regular_session(interval: str, exchange_timezone: str) -> bool:
    return _is_intraday_interval(interval) and exchange_timezone == MARKET_TZ_NAME


def _range_to_daily_points(data_range: str) -> int:
    return {
        "5d": 5,
        "1mo": 22,
        "3mo": 66,
        "6mo": 132,
        "1y": 252,
        "2y": 504,
        "5y": 1260,
    }.get(data_range, 252)
