"""Reusable technical indicators for strategy modules."""

from __future__ import annotations

import math


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


def rolling_stddev(values: list[float], window: int) -> list[float | None]:
    """Return rolling population standard deviation."""

    if window < 1:
        raise ValueError("window must be greater than zero")

    result: list[float | None] = []
    for index in range(len(values)):
        if index + 1 < window:
            result.append(None)
            continue
        sample = values[index + 1 - window : index + 1]
        mean = sum(sample) / window
        variance = sum((value - mean) ** 2 for value in sample) / window
        result.append(round(math.sqrt(variance), 4))
    return result


def relative_strength_index(values: list[float], window: int = 14) -> list[float | None]:
    """Return RSI using Wilder's smoothing."""

    if window < 1:
        raise ValueError("window must be greater than zero")
    if not values:
        return []

    result: list[float | None] = [None] * len(values)
    if len(values) <= window:
        return result

    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, window + 1):
        change = values[index] - values[index - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    average_gain = sum(gains) / window
    average_loss = sum(losses) / window
    result[window] = _rsi_value(average_gain, average_loss)

    for index in range(window + 1, len(values)):
        change = values[index] - values[index - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        average_gain = (average_gain * (window - 1) + gain) / window
        average_loss = (average_loss * (window - 1) + loss) / window
        result[index] = _rsi_value(average_gain, average_loss)

    return result


def bollinger_bands(
    values: list[float],
    window: int = 20,
    stddev_multiplier: float = 2.0,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Return lower, middle, and upper Bollinger Bands."""

    if stddev_multiplier <= 0:
        raise ValueError("stddev_multiplier must be greater than zero")

    middle = simple_moving_average(values, window)
    deviations = rolling_stddev(values, window)
    lower: list[float | None] = []
    upper: list[float | None] = []

    for average, deviation in zip(middle, deviations):
        if average is None or deviation is None:
            lower.append(None)
            upper.append(None)
        else:
            lower.append(round(average - stddev_multiplier * deviation, 4))
            upper.append(round(average + stddev_multiplier * deviation, 4))
    return lower, middle, upper


def momentum(values: list[float], window: int = 60) -> list[float | None]:
    """Return percentage momentum over a lookback window."""

    if window < 1:
        raise ValueError("window must be greater than zero")

    result: list[float | None] = []
    for index, value in enumerate(values):
        if index < window or values[index - window] == 0:
            result.append(None)
        else:
            result.append(round(((value / values[index - window]) - 1) * 100, 4))
    return result


def _rsi_value(average_gain: float, average_loss: float) -> float:
    if average_loss == 0:
        return 100.0
    relative_strength = average_gain / average_loss
    return round(100 - (100 / (1 + relative_strength)), 4)
