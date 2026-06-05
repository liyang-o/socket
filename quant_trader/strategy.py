"""Extensible strategy registry and signal generators."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

from .indicators import (
    bollinger_bands,
    momentum,
    relative_strength_index,
    simple_moving_average,
)
from .market_calendar import market_time_label
from .market_data import Bar


DEFAULT_STRATEGY = "sma_cross"


@dataclass(frozen=True)
class StrategyPoint:
    """Price bar enriched with indicator and signal state."""

    time: str
    time_et: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    fast_sma: float | None
    slow_sma: float | None
    signal: str
    rsi: float | None = None
    bb_lower: float | None = None
    bb_middle: float | None = None
    bb_upper: float | None = None
    momentum: float | None = None

    def to_dict(self) -> dict[str, float | int | str | None]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyConfig:
    """Reusable indicator and strategy parameters."""

    fast_window: int = 12
    slow_window: int = 26
    rsi_window: int = 14
    rsi_oversold: float = 30
    rsi_overbought: float = 70
    bollinger_window: int = 20
    bollinger_stddev: float = 2.0
    momentum_window: int = 60
    top_n: int = 1


@dataclass(frozen=True)
class StrategySpec:
    """Metadata for a registered strategy."""

    key: str
    label: str
    category: str
    description: str
    portfolio_level: bool = False

    def to_dict(self) -> dict[str, str | bool]:
        return asdict(self)


SignalGenerator = Callable[[list[Bar], StrategyConfig], list[StrategyPoint]]


STRATEGY_SPECS: dict[str, StrategySpec] = {
    "sma_cross": StrategySpec(
        key="sma_cross",
        label="SMA 双均线趋势",
        category="trend",
        description="fast SMA 上穿 slow SMA 买入，下穿卖出。适合趋势行情，震荡市容易反复交易。",
    ),
    "rsi_reversion": StrategySpec(
        key="rsi_reversion",
        label="RSI 均值回归",
        category="mean_reversion",
        description="RSI 跌破超卖阈值后等待回升买入，RSI 进入超买区卖出。适合短周期回归。",
    ),
    "bollinger_reversion": StrategySpec(
        key="bollinger_reversion",
        label="布林带均值回归",
        category="mean_reversion",
        description="价格跌破下轨后反弹买入，回到中轨附近卖出。适合区间震荡行情。",
    ),
    "hybrid_reversion": StrategySpec(
        key="hybrid_reversion",
        label="RSI + 布林带混合",
        category="hybrid",
        description="同时满足 RSI 超卖和价格接近布林下轨才买入，用中轨或 RSI 修复退出。",
    ),
    "momentum_rotation": StrategySpec(
        key="momentum_rotation",
        label="多资产动量轮动",
        category="portfolio",
        description="按 lookback 动量给股票排序，持有正动量最强标的。适合相对强弱轮动演示。",
        portfolio_level=True,
    ),
}


def sma_crossover_signals(
    bars: list[Bar],
    fast_window: int = 12,
    slow_window: int = 26,
) -> list[StrategyPoint]:
    """Backward-compatible SMA crossover helper."""

    return _sma_cross_signals(
        bars,
        StrategyConfig(fast_window=fast_window, slow_window=slow_window),
    )


def available_strategies() -> list[dict[str, str | bool]]:
    """Return strategies in UI-friendly form."""

    return [spec.to_dict() for spec in STRATEGY_SPECS.values()]


def strategy_spec(strategy_name: str) -> StrategySpec:
    """Return metadata for a strategy key."""

    key = normalize_strategy_name(strategy_name)
    return STRATEGY_SPECS[key]


def normalize_strategy_name(strategy_name: str | None) -> str:
    """Validate and normalize a strategy key."""

    key = (strategy_name or DEFAULT_STRATEGY).strip().lower()
    if key not in STRATEGY_SPECS:
        allowed = ", ".join(STRATEGY_SPECS)
        raise ValueError(f"unknown strategy '{strategy_name}'. allowed: {allowed}")
    return key


def generate_signals(
    bars: list[Bar],
    strategy_name: str = DEFAULT_STRATEGY,
    config: StrategyConfig | None = None,
) -> list[StrategyPoint]:
    """Generate strategy points for a registered symbol-level strategy."""

    key = normalize_strategy_name(strategy_name)
    spec = STRATEGY_SPECS[key]
    if spec.portfolio_level:
        return _momentum_points(bars, config or StrategyConfig())

    generator = _SIGNAL_GENERATORS[key]
    return generator(bars, config or StrategyConfig())


def _sma_cross_signals(bars: list[Bar], config: StrategyConfig) -> list[StrategyPoint]:
    if config.fast_window >= config.slow_window:
        raise ValueError("fast_window must be smaller than slow_window")
    if not bars:
        return []

    closes = [bar.close for bar in bars]
    fast = simple_moving_average(closes, config.fast_window)
    slow = simple_moving_average(closes, config.slow_window)

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
                time_et=bar.time_et or market_time_label(bar.time),
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


def _rsi_reversion_signals(bars: list[Bar], config: StrategyConfig) -> list[StrategyPoint]:
    closes = [bar.close for bar in bars]
    rsi_values = relative_strength_index(closes, config.rsi_window)
    points: list[StrategyPoint] = []
    previous_rsi: float | None = None

    for index, bar in enumerate(bars):
        current_rsi = rsi_values[index]
        signal = "hold"
        if previous_rsi is not None and current_rsi is not None:
            if previous_rsi < config.rsi_oversold and current_rsi >= config.rsi_oversold:
                signal = "buy"
            elif previous_rsi < config.rsi_overbought <= current_rsi:
                signal = "sell"

        points.append(_point(bar, signal=signal, rsi=current_rsi))
        if current_rsi is not None:
            previous_rsi = current_rsi

    return points


def _bollinger_reversion_signals(bars: list[Bar], config: StrategyConfig) -> list[StrategyPoint]:
    closes = [bar.close for bar in bars]
    lower, middle, upper = bollinger_bands(
        closes,
        config.bollinger_window,
        config.bollinger_stddev,
    )
    points: list[StrategyPoint] = []
    previous_close: float | None = None
    previous_lower: float | None = None
    previous_middle: float | None = None

    for index, bar in enumerate(bars):
        signal = "hold"
        current_lower = lower[index]
        current_middle = middle[index]
        if None not in (previous_close, previous_lower, previous_middle, current_lower, current_middle):
            crossed_below_lower = previous_close >= previous_lower and bar.close < current_lower
            crossed_above_middle = previous_close <= previous_middle and bar.close > current_middle
            if crossed_below_lower:
                signal = "buy"
            elif crossed_above_middle:
                signal = "sell"

        points.append(
            _point(
                bar,
                signal=signal,
                bb_lower=current_lower,
                bb_middle=current_middle,
                bb_upper=upper[index],
            )
        )
        previous_close = bar.close
        if current_lower is not None:
            previous_lower = current_lower
        if current_middle is not None:
            previous_middle = current_middle

    return points


def _hybrid_reversion_signals(bars: list[Bar], config: StrategyConfig) -> list[StrategyPoint]:
    closes = [bar.close for bar in bars]
    rsi_values = relative_strength_index(closes, config.rsi_window)
    lower, middle, upper = bollinger_bands(
        closes,
        config.bollinger_window,
        config.bollinger_stddev,
    )
    points: list[StrategyPoint] = []
    armed = False

    for index, bar in enumerate(bars):
        current_rsi = rsi_values[index]
        current_lower = lower[index]
        current_middle = middle[index]
        signal = "hold"
        if current_rsi is not None and current_lower is not None:
            oversold_near_band = current_rsi <= config.rsi_oversold and bar.close <= current_lower
            if oversold_near_band:
                armed = True
            elif armed and current_middle is not None and bar.close >= current_middle:
                signal = "buy"
                armed = False
            elif current_rsi >= config.rsi_overbought:
                signal = "sell"
                armed = False

        points.append(
            _point(
                bar,
                signal=signal,
                rsi=current_rsi,
                bb_lower=current_lower,
                bb_middle=current_middle,
                bb_upper=upper[index],
            )
        )

    return points


def _momentum_points(bars: list[Bar], config: StrategyConfig) -> list[StrategyPoint]:
    closes = [bar.close for bar in bars]
    momentum_values = momentum(closes, config.momentum_window)
    return [
        _point(bar, signal="hold", momentum=momentum_values[index])
        for index, bar in enumerate(bars)
    ]


def _point(
    bar: Bar,
    *,
    signal: str,
    fast_sma: float | None = None,
    slow_sma: float | None = None,
    rsi: float | None = None,
    bb_lower: float | None = None,
    bb_middle: float | None = None,
    bb_upper: float | None = None,
    momentum: float | None = None,
) -> StrategyPoint:
    return StrategyPoint(
        time=bar.time,
        time_et=bar.time_et or market_time_label(bar.time),
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
        fast_sma=fast_sma,
        slow_sma=slow_sma,
        signal=signal,
        rsi=rsi,
        bb_lower=bb_lower,
        bb_middle=bb_middle,
        bb_upper=bb_upper,
        momentum=momentum,
    )


_SIGNAL_GENERATORS: dict[str, SignalGenerator] = {
    "sma_cross": _sma_cross_signals,
    "rsi_reversion": _rsi_reversion_signals,
    "bollinger_reversion": _bollinger_reversion_signals,
    "hybrid_reversion": _hybrid_reversion_signals,
}
