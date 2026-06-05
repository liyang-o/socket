"""Cross-sectional factor scoring utilities."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import statistics

from .indicators import simple_moving_average
from .market_data import Bar


@dataclass(frozen=True)
class FactorScore:
    symbol: str
    total_score: float
    momentum_60: float | None
    momentum_120: float | None
    reversal_20: float | None
    low_volatility: float | None
    liquidity_trend: float | None
    trend_filter: float | None

    def to_dict(self) -> dict[str, float | str | None]:
        return asdict(self)


FACTOR_WEIGHTS = {
    "momentum_60": 0.25,
    "momentum_120": 0.25,
    "reversal_20": 0.15,
    "low_volatility": 0.15,
    "liquidity_trend": 0.10,
    "trend_filter": 0.10,
}


def compute_factor_scores(
    bars_by_symbol: dict[str, list[Bar]],
    index: int | None = None,
) -> dict[str, FactorScore]:
    """Compute cross-sectional factor scores at one point in time."""

    raw: dict[str, dict[str, float | None]] = {}
    for symbol, bars in bars_by_symbol.items():
        if not bars:
            continue
        idx = min(index if index is not None else len(bars) - 1, len(bars) - 1)
        raw[symbol] = {
            "momentum_60": _pct_return(bars, idx, 60),
            "momentum_120": _pct_return(bars, idx, 120),
            "reversal_20": _negated(_pct_return(bars, idx, 20)),
            "low_volatility": _negated(_volatility(bars, idx, 20)),
            "liquidity_trend": _liquidity_trend(bars, idx),
            "trend_filter": _trend_filter(bars, idx),
        }

    zscores = {
        factor: _cross_sectional_zscore(raw, factor)
        for factor in FACTOR_WEIGHTS
    }
    scores: dict[str, FactorScore] = {}
    for symbol, values in raw.items():
        total = 0.0
        active_weight = 0.0
        for factor, weight in FACTOR_WEIGHTS.items():
            value = zscores[factor].get(symbol)
            if value is None:
                continue
            total += value * weight
            active_weight += weight
        normalized_total = total / active_weight if active_weight else 0.0
        scores[symbol] = FactorScore(
            symbol=symbol,
            total_score=round(normalized_total, 4),
            momentum_60=values["momentum_60"],
            momentum_120=values["momentum_120"],
            reversal_20=values["reversal_20"],
            low_volatility=values["low_volatility"],
            liquidity_trend=values["liquidity_trend"],
            trend_filter=values["trend_filter"],
        )
    return scores


def select_top_scores(scores: dict[str, FactorScore], top_n: int) -> list[FactorScore]:
    """Return positive-score leaders."""

    leaders = [score for score in scores.values() if score.total_score > 0]
    leaders.sort(key=lambda score: score.total_score, reverse=True)
    return leaders[: max(top_n, 1)]


def volatility_inverse_weights(
    bars_by_symbol: dict[str, list[Bar]],
    symbols: list[str],
    index: int,
    *,
    max_weight: float = 0.12,
    cash_buffer: float = 0.05,
) -> dict[str, float]:
    """Allocate selected symbols by inverse recent volatility with caps."""

    risks = {
        symbol: max(_volatility(bars_by_symbol[symbol], index, 20) or 1.0, 0.0001)
        for symbol in symbols
        if symbol in bars_by_symbol
    }
    if not risks:
        return {}

    inverse = {symbol: 1 / risk for symbol, risk in risks.items()}
    total_inverse = sum(inverse.values())
    gross_budget = max(0.0, min(1.0, 1 - cash_buffer))
    raw_weights = {
        symbol: gross_budget * value / total_inverse
        for symbol, value in inverse.items()
    }
    capped = {symbol: min(weight, max_weight) for symbol, weight in raw_weights.items()}
    capped_total = sum(capped.values())
    if capped_total <= gross_budget and capped_total > 0:
        scale = gross_budget / capped_total
        return {symbol: round(min(weight * scale, max_weight), 4) for symbol, weight in capped.items()}
    return {symbol: round(weight, 4) for symbol, weight in capped.items()}


def _pct_return(bars: list[Bar], index: int, window: int) -> float | None:
    if index < window or bars[index - window].close == 0:
        return None
    return round(((bars[index].close / bars[index - window].close) - 1) * 100, 4)


def _negated(value: float | None) -> float | None:
    return None if value is None else round(-value, 4)


def _volatility(bars: list[Bar], index: int, window: int) -> float | None:
    if index < window:
        return None
    returns = []
    for idx in range(index - window + 1, index + 1):
        previous = bars[idx - 1].close
        if previous:
            returns.append(((bars[idx].close / previous) - 1) * 100)
    if len(returns) < 2:
        return None
    return round(statistics.pstdev(returns), 4)


def _liquidity_trend(bars: list[Bar], index: int) -> float | None:
    if index < 60:
        return None
    recent = sum(bar.volume for bar in bars[index - 19 : index + 1]) / 20
    baseline = sum(bar.volume for bar in bars[index - 59 : index + 1]) / 60
    if baseline == 0:
        return None
    return round(((recent / baseline) - 1) * 100, 4)


def _trend_filter(bars: list[Bar], index: int) -> float | None:
    closes = [bar.close for bar in bars[: index + 1]]
    window = 200 if len(closes) >= 200 else min(60, len(closes))
    if window < 20:
        return None
    average = simple_moving_average(closes, window)[-1]
    if average is None or average == 0:
        return None
    return round(((bars[index].close / average) - 1) * 100, 4)


def _cross_sectional_zscore(
    raw: dict[str, dict[str, float | None]],
    factor: str,
) -> dict[str, float | None]:
    values = [row[factor] for row in raw.values() if row[factor] is not None]
    if len(values) < 2:
        return {symbol: None for symbol in raw}
    mean = statistics.mean(values)
    stdev = statistics.pstdev(values) or 1.0
    return {
        symbol: None if row[factor] is None else (row[factor] - mean) / stdev
        for symbol, row in raw.items()
    }
