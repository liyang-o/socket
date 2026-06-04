"""Simple moving-average crossover strategy.

This follows the same teaching idea made popular by projects such as
backtesting.py and vectorbt: calculate a fast and a slow moving average, buy
when fast crosses above slow, and sell when fast crosses below slow.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .market_data import Bar


@dataclass(frozen=True)
class StrategyPoint:
    """Price bar enriched with indicator and signal state."""

    time: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    fast_sma: float | None
    slow_sma: float | None
    signal: str

    def to_dict(self) -> dict[str, float | int | str | None]:
        return asdict(self)


def simple_moving_average(values: list[float], window: int) -> list[float | None]:
    """Return an SMA series with ``None`` until enough data is available."""

    if window < 1:
        raise ValueError("window must be greater than zero")

    result: list[float | None] = []
    running_sum = 0.0
    for index, value in enumerate(values):
        running_sum += value
        if index >= window:
            running_sum -= values[index - window]

        if index + 1 < window:
            result.append(None)
        else:
            result.append(round(running_sum / window, 4))
    return result


def sma_crossover_signals(
    bars: list[Bar],
    fast_window: int = 12,
    slow_window: int = 26,
) -> list[StrategyPoint]:
    """Annotate bars with SMA crossover buy/sell/hold signals."""

    if fast_window >= slow_window:
        raise ValueError("fast_window must be smaller than slow_window")
    if not bars:
        return []

    closes = [bar.close for bar in bars]
    fast = simple_moving_average(closes, fast_window)
    slow = simple_moving_average(closes, slow_window)

    points: list[StrategyPoint] = []
    previous_fast: float | None = None
    previous_slow: float | None = None

    for index, bar in enumerate(bars):
        current_fast = fast[index]
        current_slow = slow[index]
        signal = "hold"

        if None not in (previous_fast, previous_slow, current_fast, current_slow):
            crossed_up = previous_fast <= previous_slow and current_fast > current_slow
            crossed_down = previous_fast >= previous_slow and current_fast < current_slow
            if crossed_up:
                signal = "buy"
            elif crossed_down:
                signal = "sell"

        points.append(
            StrategyPoint(
                time=bar.time,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                fast_sma=current_fast,
                slow_sma=current_slow,
                signal=signal,
            )
        )

        if current_fast is not None and current_slow is not None:
            previous_fast = current_fast
            previous_slow = current_slow

    return points
