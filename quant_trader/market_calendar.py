"""US stock market calendar helpers.

The rules here cover common NYSE regular-session behavior well enough for a
paper-trading demo: weekdays, major exchange holidays, Good Friday, and common
early closes. It is intentionally dependency-free; production trading should use
an exchange calendar data source.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


MARKET_TZ_NAME = "America/New_York"
MARKET_TZ = ZoneInfo(MARKET_TZ_NAME)
CHINA_TZ_NAME = "Asia/Shanghai"
CHINA_TZ = ZoneInfo(CHINA_TZ_NAME)
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
EARLY_CLOSE = time(13, 0)
CHINA_MORNING_CLOSE = time(11, 30)
CHINA_AFTERNOON_OPEN = time(13, 0)
CHINA_CLOSE = time(15, 0)


@dataclass(frozen=True)
class SessionInfo:
    """Market session state for display and filtering."""

    timezone: str
    session_date: str
    is_trading_day: bool
    is_open: bool
    status: str
    reason: str
    open_time_et: str | None
    close_time_et: str | None
    generated_at_utc: str
    generated_at_et: str

    def to_dict(self) -> dict[str, bool | str | None]:
        return asdict(self)


def to_market_time(value: datetime | str) -> datetime:
    """Convert a UTC/local aware datetime or ISO string to New York time."""

    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    else:
        parsed = value

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(MARKET_TZ)


def to_utc_iso(value: datetime) -> str:
    """Return a stable UTC ISO timestamp."""

    if value.tzinfo is None:
        value = value.replace(tzinfo=MARKET_TZ)
    return value.astimezone(timezone.utc).isoformat()


def market_time_label(value: datetime | str) -> str:
    """Format a timestamp as a concise exchange-time label."""

    market_dt = to_market_time(value)
    return market_dt.strftime("%Y-%m-%d %H:%M ET")


def timezone_time_label(value: datetime | str, timezone_name: str = MARKET_TZ_NAME) -> str:
    """Format a timestamp in an exchange/local timezone."""

    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    else:
        parsed = value

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    try:
        target_tz = ZoneInfo(timezone_name)
    except Exception:
        target_tz = MARKET_TZ
    return parsed.astimezone(target_tz).strftime("%Y-%m-%d %H:%M %Z")


def session_bounds(session_date: date) -> tuple[datetime, datetime] | None:
    """Return open/close datetimes for a session date, or None if closed."""

    holiday_reason = market_holiday_reason(session_date)
    if holiday_reason is not None:
        return None

    close_time = EARLY_CLOSE if is_early_close(session_date) else REGULAR_CLOSE
    open_dt = datetime.combine(session_date, REGULAR_OPEN, tzinfo=MARKET_TZ)
    close_dt = datetime.combine(session_date, close_time, tzinfo=MARKET_TZ)
    return open_dt, close_dt


def exchange_session_bounds(
    session_date: date,
    timezone_name: str = MARKET_TZ_NAME,
) -> list[tuple[datetime, datetime]]:
    """Return one or more regular-session windows for a supported exchange."""

    if timezone_name == CHINA_TZ_NAME:
        if china_holiday_reason(session_date) is not None:
            return []
        return [
            (
                datetime.combine(session_date, REGULAR_OPEN, tzinfo=CHINA_TZ),
                datetime.combine(session_date, CHINA_MORNING_CLOSE, tzinfo=CHINA_TZ),
            ),
            (
                datetime.combine(session_date, CHINA_AFTERNOON_OPEN, tzinfo=CHINA_TZ),
                datetime.combine(session_date, CHINA_CLOSE, tzinfo=CHINA_TZ),
            ),
        ]

    bounds = session_bounds(session_date)
    return [bounds] if bounds is not None else []


def market_session_info(now: datetime | None = None, timezone_name: str = MARKET_TZ_NAME) -> SessionInfo:
    """Describe the current session in exchange time."""

    if timezone_name == CHINA_TZ_NAME:
        return _china_session_info(now)

    generated_at = now or datetime.now(timezone.utc)
    generated_et = generated_at.astimezone(MARKET_TZ)
    session_date = generated_et.date()
    bounds = session_bounds(session_date)

    if bounds is None:
        reason = market_holiday_reason(session_date) or "Market closed"
        return SessionInfo(
            timezone=MARKET_TZ_NAME,
            session_date=session_date.isoformat(),
            is_trading_day=False,
            is_open=False,
            status="closed",
            reason=reason,
            open_time_et=None,
            close_time_et=None,
            generated_at_utc=generated_at.astimezone(timezone.utc).isoformat(),
            generated_at_et=market_time_label(generated_at),
        )

    open_dt, close_dt = bounds
    is_open = open_dt <= generated_et <= close_dt
    if is_open:
        status = "open"
        reason = "Regular session is open"
    elif generated_et < open_dt:
        status = "pre_market"
        reason = "Regular session has not opened"
    else:
        status = "after_hours"
        reason = "Regular session has closed"

    return SessionInfo(
        timezone=MARKET_TZ_NAME,
        session_date=session_date.isoformat(),
        is_trading_day=True,
        is_open=is_open,
        status=status,
        reason=reason,
        open_time_et=market_time_label(open_dt),
        close_time_et=market_time_label(close_dt),
        generated_at_utc=generated_at.astimezone(timezone.utc).isoformat(),
        generated_at_et=market_time_label(generated_at),
    )


def filter_regular_session_bars(bars: list, now: datetime | None = None) -> list:
    """Keep bars within the active US regular trading session."""

    if not bars:
        return []

    reference = now or datetime.now(timezone.utc)
    target_session = _session_for_bars(bars, reference)
    bounds = session_bounds(target_session)
    if bounds is None:
        return []

    open_dt, close_dt = bounds
    return [
        bar
        for bar in bars
        if open_dt <= to_market_time(bar.time) <= close_dt
    ]


def filter_exchange_session_bars(
    bars: list,
    timezone_name: str = MARKET_TZ_NAME,
    now: datetime | None = None,
) -> list:
    """Keep bars within the supported exchange's regular session."""

    if timezone_name == MARKET_TZ_NAME:
        return filter_regular_session_bars(bars, now)
    if timezone_name != CHINA_TZ_NAME:
        return bars
    if not bars:
        return []

    latest_day = _local_time(bars[-1].time, timezone_name).date()
    windows = exchange_session_bounds(latest_day, timezone_name)
    return [
        bar
        for bar in bars
        if any(start <= _local_time(bar.time, timezone_name) <= end for start, end in windows)
    ]


def previous_trading_day(day: date) -> date:
    """Return the nearest trading day on or before ``day``."""

    current = day
    while session_bounds(current) is None:
        current -= timedelta(days=1)
    return current


def previous_exchange_trading_day(day: date, timezone_name: str = MARKET_TZ_NAME) -> date:
    current = day
    while not exchange_session_bounds(current, timezone_name):
        current -= timedelta(days=1)
    return current


def market_holiday_reason(day: date) -> str | None:
    """Return the close reason for a date, or None for an open trading day."""

    if day.weekday() >= 5:
        return "Weekend"

    holidays = {
        _observed(date(day.year, 1, 1)): "New Year's Day",
        _nth_weekday(day.year, 1, 0, 3): "Martin Luther King Jr. Day",
        _nth_weekday(day.year, 2, 0, 3): "Presidents' Day",
        _good_friday(day.year): "Good Friday",
        _last_weekday(day.year, 5, 0): "Memorial Day",
        _observed(date(day.year, 6, 19)): "Juneteenth",
        _observed(date(day.year, 7, 4)): "Independence Day",
        _nth_weekday(day.year, 9, 0, 1): "Labor Day",
        _nth_weekday(day.year, 11, 3, 4): "Thanksgiving Day",
        _observed(date(day.year, 12, 25)): "Christmas Day",
    }
    return holidays.get(day)


def china_holiday_reason(day: date) -> str | None:
    """Basic A-share trading calendar fallback.

    This intentionally covers weekends only. Exchange holiday makeup days change
    each year and should be sourced from an official calendar for production.
    """

    if day.weekday() >= 5:
        return "Weekend"
    return None


def is_early_close(day: date) -> bool:
    """Return True for common 1pm ET NYSE early closes."""

    if market_holiday_reason(day) is not None:
        return False

    # Day after Thanksgiving.
    if day == _nth_weekday(day.year, 11, 3, 4) + timedelta(days=1):
        return True

    # Christmas Eve, when it falls on a weekday trading day.
    if day.month == 12 and day.day == 24 and day.weekday() < 5:
        return True

    # July 3 when Independence Day is not observed that same weekday.
    if day.month == 7 and day.day == 3 and day.weekday() < 5:
        return True

    return False


def _session_for_bars(bars: list, reference: datetime) -> date:
    latest_bar_day = to_market_time(bars[-1].time).date()
    reference_day = reference.astimezone(MARKET_TZ).date()
    return latest_bar_day if latest_bar_day <= reference_day else reference_day


def _china_session_info(now: datetime | None) -> SessionInfo:
    generated_at = now or datetime.now(timezone.utc)
    generated_local = generated_at.astimezone(CHINA_TZ)
    session_date = generated_local.date()
    windows = exchange_session_bounds(session_date, CHINA_TZ_NAME)

    if not windows:
        return SessionInfo(
            timezone=CHINA_TZ_NAME,
            session_date=session_date.isoformat(),
            is_trading_day=False,
            is_open=False,
            status="closed",
            reason=china_holiday_reason(session_date) or "Market closed",
            open_time_et=None,
            close_time_et=None,
            generated_at_utc=generated_at.astimezone(timezone.utc).isoformat(),
            generated_at_et=timezone_time_label(generated_at, CHINA_TZ_NAME),
        )

    is_open = any(start <= generated_local <= end for start, end in windows)
    if is_open:
        status = "open"
        reason = "Regular session is open"
    elif windows[0][1] < generated_local < windows[1][0]:
        status = "lunch_break"
        reason = "Midday break"
    elif generated_local < windows[0][0]:
        status = "pre_market"
        reason = "Regular session has not opened"
    else:
        status = "after_hours"
        reason = "Regular session has closed"

    return SessionInfo(
        timezone=CHINA_TZ_NAME,
        session_date=session_date.isoformat(),
        is_trading_day=True,
        is_open=is_open,
        status=status,
        reason=reason,
        open_time_et=timezone_time_label(windows[0][0], CHINA_TZ_NAME),
        close_time_et=timezone_time_label(windows[-1][1], CHINA_TZ_NAME),
        generated_at_utc=generated_at.astimezone(timezone.utc).isoformat(),
        generated_at_et=timezone_time_label(generated_at, CHINA_TZ_NAME),
    )


def _local_time(value: datetime | str, timezone_name: str) -> datetime:
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        parsed = value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(ZoneInfo(timezone_name))


def _observed(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _nth_weekday(year: int, month: int, weekday: int, nth: int) -> date:
    current = date(year, month, 1)
    while current.weekday() != weekday:
        current += timedelta(days=1)
    return current + timedelta(days=7 * (nth - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        current = date(year, 12, 31)
    else:
        current = date(year, month + 1, 1) - timedelta(days=1)
    while current.weekday() != weekday:
        current -= timedelta(days=1)
    return current


def _good_friday(year: int) -> date:
    # Anonymous Gregorian algorithm, then subtract two days from Easter.
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day) - timedelta(days=2)
