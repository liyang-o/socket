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
    CHINA_TZ_NAME,
    MARKET_TZ_NAME,
    MARKET_TZ,
    exchange_session_bounds,
    filter_exchange_session_bars,
    filter_regular_session_bars,
    market_session_info,
    market_time_label,
    previous_exchange_trading_day,
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

    raw = symbol.upper().strip()
    if raw.startswith("SH") and raw[2:].isdigit():
        return f"{raw[2:]}.SS"
    if raw.startswith("SZ") and raw[2:].isdigit():
        return f"{raw[2:]}.SZ"

    cleaned = "".join(ch for ch in raw if ch.isalnum() or ch in ".=-")
    if not cleaned:
        raise ValueError("symbol cannot be empty")
    if cleaned.isdigit() and len(cleaned) == 6:
        if cleaned.startswith(("5", "6", "9")):
            return f"{cleaned}.SS"
        return f"{cleaned}.SZ"
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
    fallback_timezone = infer_exchange_timezone(normalized)
    if os.getenv("QUANT_TRADER_OFFLINE") == "1":
        return MarketSeries(
            normalized,
            "sample",
            sample_bars(normalized, data_range=data_range, interval=interval),
            fallback_timezone,
            data_range=data_range,
            interval=interval,
        )

    try:
        bars, exchange_timezone = _fetch_yahoo_chart(normalized, data_range, interval)
        if _should_filter_regular_session(interval, exchange_timezone):
            bars = filter_exchange_session_bars(bars, exchange_timezone)
    except (HTTPError, URLError, TimeoutError, KeyError, IndexError, TypeError, ValueError):
        bars = []
        exchange_timezone = fallback_timezone

    if len(bars) >= _min_required_bars(interval):
        _save_cached_bars(normalized, bars, exchange_timezone, data_range, interval)
        return MarketSeries(normalized, "yahoo", bars, exchange_timezone, data_range, interval)

    cached_bars = _load_cached_bars(normalized, data_range, interval)
    if len(cached_bars) >= _min_required_bars(interval):
        return MarketSeries(normalized, "cache", cached_bars, fallback_timezone, data_range, interval)

    if len(bars) < _min_required_bars(interval):
        return MarketSeries(
            normalized,
            "sample",
            sample_bars(normalized, data_range=data_range, interval=interval),
            fallback_timezone,
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

    exchange_timezone = infer_exchange_timezone(symbol)
    if _is_intraday_interval(interval):
        return sample_intraday(symbol, exchange_timezone=exchange_timezone)
    return sample_history(symbol, points=_range_to_daily_points(data_range), exchange_timezone=exchange_timezone)


def sample_intraday(
    symbol: str,
    points: int = 391,
    now: datetime | None = None,
    exchange_timezone: str | None = None,
) -> list[Bar]:
    """Generate realistic-looking intraday data when live data is unavailable."""

    seed = sum(ord(ch) for ch in symbol)
    base_price = 70 + seed % 180
    trend = ((seed % 9) - 4) / 900
    exchange_timezone = exchange_timezone or infer_exchange_timezone(symbol)
    windows = _sample_session_windows(now, exchange_timezone)
    timestamps = [
        start + timedelta(minutes=minute)
        for start, end in windows
        for minute in range(int((end - start).total_seconds() // 60) + 1)
    ][-points:]

    bars: list[Bar] = []
    previous_close = float(base_price)
    for index, current_time in enumerate(timestamps):
        progress = index / max(len(timestamps) - 1, 1)
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
                time_local=timezone_time_label(current_time, exchange_timezone),
                timezone=exchange_timezone,
            )
        )
        previous_close = close
    return bars


def sample_history(
    symbol: str,
    points: int = 252,
    now: datetime | None = None,
    exchange_timezone: str | None = None,
) -> list[Bar]:
    """Generate daily historical bars on recent US trading days."""

    exchange_timezone = exchange_timezone or infer_exchange_timezone(symbol)
    seed = sum(ord(ch) for ch in symbol)
    base_price = 70 + seed % 180
    reference = now or datetime.now(timezone.utc)
    current_day = previous_exchange_trading_day(
        reference.astimezone(_zone(exchange_timezone)).date(),
        exchange_timezone,
    )
    trading_days = []
    while len(trading_days) < points:
        trading_days.append(current_day)
        current_day = previous_exchange_trading_day(current_day - timedelta(days=1), exchange_timezone)
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
        windows = exchange_session_bounds(trading_day, exchange_timezone)
        if not windows:
            continue
        timestamp = windows[-1][1]

        bars.append(
            Bar(
                time=to_utc_iso(timestamp),
                open=round(previous_close, 4),
                high=round(high, 4),
                low=round(low, 4),
                close=round(close, 4),
                volume=volume,
                time_et=market_time_label(timestamp),
                time_local=timezone_time_label(timestamp, exchange_timezone),
                timezone=exchange_timezone,
            )
        )
        previous_close = close
    return bars


def _sample_session_windows(now: datetime | None, exchange_timezone: str) -> list[tuple[datetime, datetime]]:
    reference = now or datetime.now(timezone.utc)
    info = market_session_info(reference, exchange_timezone)
    reference_local = reference.astimezone(_zone(exchange_timezone)).replace(second=0, microsecond=0)

    if info.is_trading_day and info.status == "open":
        windows = exchange_session_bounds(reference_local.date(), exchange_timezone)
        if not windows:
            raise ValueError("trading session unexpectedly unavailable")
        active_window = next(
            ((start, end) for start, end in windows if start <= reference_local <= end),
            windows[-1],
        )
        completed = [(start, end) for start, end in windows if end < active_window[0]]
        return completed + [(active_window[0], min(reference_local, active_window[1]))]

    if info.is_trading_day and info.status == "after_hours":
        session_date = reference_local.date()
    else:
        session_date = previous_exchange_trading_day(reference_local.date() - timedelta(days=1), exchange_timezone)

    windows = exchange_session_bounds(session_date, exchange_timezone)
    if not windows:
        raise ValueError("trading session unexpectedly unavailable")
    return windows


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _is_intraday_interval(interval: str) -> bool:
    normalized = interval.lower()
    return normalized.endswith("m") or normalized.endswith("h")


def _should_filter_regular_session(interval: str, exchange_timezone: str) -> bool:
    return _is_intraday_interval(interval) and exchange_timezone in {MARKET_TZ_NAME, CHINA_TZ_NAME}


def infer_exchange_timezone(symbol: str) -> str:
    normalized = normalize_symbol(symbol) if not symbol.endswith((".SS", ".SZ")) else symbol
    if normalized.endswith((".SS", ".SZ")):
        return CHINA_TZ_NAME
    return MARKET_TZ_NAME


def _zone(timezone_name: str):
    from zoneinfo import ZoneInfo

    return ZoneInfo(timezone_name)


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


def _min_required_bars(interval: str) -> int:
    return 30 if _is_intraday_interval(interval) else 5


def _save_cached_bars(
    symbol: str,
    bars: list[Bar],
    exchange_timezone: str,
    data_range: str,
    interval: str,
) -> None:
    try:
        from .storage import default_store

        default_store().save_bars(
            symbol,
            bars,
            source="yahoo",
            exchange_timezone=exchange_timezone,
            data_range=data_range,
            interval=interval,
        )
    except OSError:
        return


def _load_cached_bars(symbol: str, data_range: str, interval: str) -> list[Bar]:
    try:
        from .storage import default_store

        return default_store().load_bars(symbol, data_range=data_range, interval=interval)
    except OSError:
        return []
