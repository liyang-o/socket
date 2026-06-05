"""Run strategy signals through the paper broker."""

from __future__ import annotations

from .broker import EquityPoint, PaperBroker
from .factors import compute_factor_scores, select_top_scores, volatility_inverse_weights
from .market_calendar import market_session_info, market_time_label
from .market_data import MarketSeries
from .metrics import performance_report
from .strategy import (
    DEFAULT_STRATEGY,
    StrategyConfig,
    StrategyPoint,
    available_strategies,
    generate_signals,
    strategy_spec,
)


def simulate_portfolio(
    market: dict[str, MarketSeries],
    *,
    initial_cash: float = 100_000,
    fast_window: int = 12,
    slow_window: int = 26,
    strategy_name: str = DEFAULT_STRATEGY,
    rsi_window: int = 14,
    rsi_oversold: float = 30,
    rsi_overbought: float = 70,
    bollinger_window: int = 20,
    bollinger_stddev: float = 2.0,
    momentum_window: int = 60,
    top_n: int = 1,
    data_range: str = "6mo",
    interval: str = "1d",
    commission_rate: float = 0.001,
) -> dict[str, object]:
    """Simulate each selected symbol, then aggregate the resulting account."""

    if initial_cash <= 0:
        raise ValueError("initial_cash must be greater than zero")
    if not market:
        raise ValueError("market data cannot be empty")

    config = StrategyConfig(
        fast_window=fast_window,
        slow_window=slow_window,
        rsi_window=rsi_window,
        rsi_oversold=rsi_oversold,
        rsi_overbought=rsi_overbought,
        bollinger_window=bollinger_window,
        bollinger_stddev=bollinger_stddev,
        momentum_window=momentum_window,
        top_n=top_n,
    )
    spec = strategy_spec(strategy_name)
    if spec.portfolio_level:
        if spec.key == "multi_factor_top":
            return _simulate_multi_factor_top(
                market,
                initial_cash=initial_cash,
                commission_rate=commission_rate,
                config=config,
                data_range=data_range,
                interval=interval,
            )
        return _simulate_momentum_rotation(
            market,
            strategy_name=spec.key,
            initial_cash=initial_cash,
            commission_rate=commission_rate,
            config=config,
            data_range=data_range,
            interval=interval,
        )

    allocation = initial_cash / len(market)
    symbol_results: dict[str, dict[str, object]] = {}
    total_equity = 0.0
    total_cash = 0.0
    total_trades = 0
    all_positions: list[dict[str, float | str]] = []
    latest_prices: dict[str, float] = {}
    latest_bar_times: dict[str, str] = {}
    latest_bar_times_et: dict[str, str] = {}
    sources: dict[str, str] = {}
    all_trades = []

    for symbol, series in market.items():
        broker = PaperBroker(cash=allocation, commission_rate=commission_rate)
        points = generate_signals(series.bars, spec.key, config)
        equity_curve = _run_symbol(symbol, broker, points)
        last_price = points[-1].close if points else 0.0
        latest_prices[symbol] = last_price
        if points:
            latest_bar_times[symbol] = points[-1].time
            latest_bar_times_et[symbol] = market_time_label(points[-1].time)
        sources[symbol] = series.source

        final_equity = broker.equity({symbol: last_price})
        total_equity += final_equity
        total_cash += broker.cash
        total_trades += len(broker.trades)
        all_trades.extend(broker.trades)
        all_positions.extend(broker.open_positions({symbol: last_price}))

        symbol_results[symbol] = {
            "source": series.source,
            "exchange_timezone": series.exchange_timezone,
            "initial_cash": round(allocation, 2),
            "cash": round(broker.cash, 2),
            "equity": round(final_equity, 2),
            "pnl": round(final_equity - allocation, 2),
            "daily_return_pct": round(((final_equity / allocation) - 1) * 100, 4),
            "last_price": round(last_price, 4),
            "latest_bar_time": points[-1].time if points else None,
            "latest_bar_time_et": market_time_label(points[-1].time) if points else None,
            "bars": [point.to_dict() for point in points],
            "trades": [trade.to_dict() for trade in broker.trades],
            "positions": broker.open_positions({symbol: last_price}),
            "equity_curve": [point.to_dict() for point in equity_curve],
        }

    return {
        "portfolio": {
            "initial_cash": round(initial_cash, 2),
            "cash": round(total_cash, 2),
            "equity": round(total_equity, 2),
            "pnl": round(total_equity - initial_cash, 2),
            "daily_return_pct": round(((total_equity / initial_cash) - 1) * 100, 4),
            "total_trades": total_trades,
            "positions": all_positions,
            "latest_prices": {key: round(value, 4) for key, value in latest_prices.items()},
            "latest_bar_times": latest_bar_times,
            "latest_bar_times_et": latest_bar_times_et,
            "sources": sources,
            "exchange_timezones": {
                symbol: series.exchange_timezone for symbol, series in market.items()
            },
            "market_session": market_session_info().to_dict(),
            "market_sessions": _market_sessions_payload(market),
            "report": performance_report(
                _aggregate_symbol_equity(symbol_results),
                all_trades,
                initial_cash=initial_cash,
            ),
        },
        "symbols": symbol_results,
        "parameters": _parameters_payload(spec.key, config, commission_rate, data_range, interval),
    }


def _run_symbol(
    symbol: str,
    broker: PaperBroker,
    points: list[StrategyPoint],
) -> list[EquityPoint]:
    equity_curve: list[EquityPoint] = []
    for point in points:
        if point.signal == "buy":
            broker.buy(symbol, point.close, point.time)
        elif point.signal == "sell":
            broker.sell_all(symbol, point.close, point.time)

        equity_curve.append(EquityPoint(point.time, round(broker.equity({symbol: point.close}), 2)))
    return equity_curve


def _simulate_momentum_rotation(
    market: dict[str, MarketSeries],
    *,
    strategy_name: str,
    initial_cash: float,
    commission_rate: float,
    config: StrategyConfig,
    data_range: str = "6mo",
    interval: str = "1d",
) -> dict[str, object]:
    spec = strategy_spec(strategy_name)
    broker = PaperBroker(cash=initial_cash, commission_rate=commission_rate)
    points_by_symbol = {
        symbol: generate_signals(series.bars, spec.key, config)
        for symbol, series in market.items()
    }
    max_points = min((len(points) for points in points_by_symbol.values()), default=0)
    symbol_results: dict[str, dict[str, object]] = {}
    equity_curve: list[EquityPoint] = []
    current_symbol: str | None = None

    for index in range(max_points):
        prices = {
            symbol: points[index].close
            for symbol, points in points_by_symbol.items()
        }
        scores = {
            symbol: points[index].momentum
            for symbol, points in points_by_symbol.items()
            if points[index].momentum is not None
        }
        target_symbol = _top_positive_momentum(scores)

        if target_symbol != current_symbol:
            if current_symbol is not None:
                sell_point = points_by_symbol[current_symbol][index]
                broker.sell_all(current_symbol, sell_point.close, sell_point.time)
                points_by_symbol[current_symbol][index] = _replace_signal(sell_point, "sell")
                current_symbol = None

            if target_symbol is not None:
                buy_point = points_by_symbol[target_symbol][index]
                broker.buy(target_symbol, buy_point.close, buy_point.time)
                points_by_symbol[target_symbol][index] = _replace_signal(buy_point, "buy")
                current_symbol = target_symbol

        timestamp = next(iter(points_by_symbol.values()))[index].time
        equity_curve.append(EquityPoint(timestamp, round(broker.equity(prices), 2)))

    latest_prices = {
        symbol: points[-1].close
        for symbol, points in points_by_symbol.items()
        if points
    }
    latest_bar_times = {
        symbol: points[-1].time
        for symbol, points in points_by_symbol.items()
        if points
    }
    latest_bar_times_et = {
        symbol: market_time_label(points[-1].time)
        for symbol, points in points_by_symbol.items()
        if points
    }
    final_equity = broker.equity(latest_prices)
    all_positions = broker.open_positions(latest_prices)

    for symbol, series in market.items():
        points = points_by_symbol[symbol]
        last_price = points[-1].close if points else 0.0
        symbol_trades = [trade for trade in broker.trades if trade.symbol == symbol]
        symbol_results[symbol] = {
            "source": series.source,
            "exchange_timezone": series.exchange_timezone,
            "initial_cash": round(initial_cash, 2),
            "cash": round(broker.cash, 2),
            "equity": round(final_equity, 2),
            "pnl": round(final_equity - initial_cash, 2),
            "daily_return_pct": round(((final_equity / initial_cash) - 1) * 100, 4),
            "last_price": round(last_price, 4),
            "latest_bar_time": points[-1].time if points else None,
            "latest_bar_time_et": market_time_label(points[-1].time) if points else None,
            "bars": [point.to_dict() for point in points],
            "trades": [trade.to_dict() for trade in symbol_trades],
            "positions": [position for position in all_positions if position["symbol"] == symbol],
            "equity_curve": [point.to_dict() for point in equity_curve],
        }

    return {
        "portfolio": {
            "initial_cash": round(initial_cash, 2),
            "cash": round(broker.cash, 2),
            "equity": round(final_equity, 2),
            "pnl": round(final_equity - initial_cash, 2),
            "daily_return_pct": round(((final_equity / initial_cash) - 1) * 100, 4),
            "total_trades": len(broker.trades),
            "positions": all_positions,
            "latest_prices": {key: round(value, 4) for key, value in latest_prices.items()},
            "latest_bar_times": latest_bar_times,
            "latest_bar_times_et": latest_bar_times_et,
            "sources": {symbol: series.source for symbol, series in market.items()},
            "exchange_timezones": {
                symbol: series.exchange_timezone for symbol, series in market.items()
            },
            "market_session": market_session_info().to_dict(),
            "market_sessions": _market_sessions_payload(market),
            "report": performance_report(equity_curve, broker.trades, initial_cash=initial_cash),
        },
        "symbols": symbol_results,
        "parameters": _parameters_payload(spec.key, config, commission_rate, data_range, interval),
    }


def _simulate_multi_factor_top(
    market: dict[str, MarketSeries],
    *,
    initial_cash: float,
    commission_rate: float,
    config: StrategyConfig,
    data_range: str = "6mo",
    interval: str = "1d",
) -> dict[str, object]:
    spec = strategy_spec("multi_factor_top")
    broker = PaperBroker(cash=initial_cash, commission_rate=commission_rate)
    points_by_symbol = {
        symbol: generate_signals(series.bars, "momentum_rotation", config)
        for symbol, series in market.items()
    }
    bars_by_symbol = {symbol: series.bars for symbol, series in market.items()}
    max_points = min((len(points) for points in points_by_symbol.values()), default=0)
    symbol_results: dict[str, dict[str, object]] = {}
    equity_curve: list[EquityPoint] = []
    factor_history: dict[str, list[dict[str, object]]] = {symbol: [] for symbol in market}
    current_targets: set[str] = set()

    for index in range(max_points):
        prices = {symbol: points[index].close for symbol, points in points_by_symbol.items()}
        factor_scores = compute_factor_scores(bars_by_symbol, index)
        leaders = select_top_scores(factor_scores, config.top_n)
        target_symbols = [leader.symbol for leader in leaders]
        target_weights = volatility_inverse_weights(
            bars_by_symbol,
            target_symbols,
            index,
            max_weight=0.12,
            cash_buffer=0.05,
        )
        target_set = set(target_weights)

        for symbol, score in factor_scores.items():
            factor_history[symbol].append(score.to_dict())

        if target_set != current_targets:
            for symbol in list(current_targets - target_set):
                point = points_by_symbol[symbol][index]
                broker.sell_all(symbol, point.close, point.time)
                points_by_symbol[symbol][index] = _replace_signal(point, "sell", factor_scores.get(symbol))

            current_equity = broker.equity(prices)
            for symbol, weight in target_weights.items():
                point = points_by_symbol[symbol][index]
                target_value = current_equity * weight
                current_value = broker.positions.get(symbol).market_value(point.close) if symbol in broker.positions else 0.0
                budget = max(0.0, target_value - current_value)
                if budget > 0:
                    broker.buy_budget(symbol, point.close, point.time, budget)
                    points_by_symbol[symbol][index] = _replace_signal(point, "buy", factor_scores.get(symbol))

            current_targets = target_set

        timestamp = next(iter(points_by_symbol.values()))[index].time
        equity_curve.append(EquityPoint(timestamp, round(broker.equity(prices), 2)))

    latest_prices = {symbol: points[-1].close for symbol, points in points_by_symbol.items() if points}
    all_positions = broker.open_positions(latest_prices)
    final_equity = broker.equity(latest_prices)

    for symbol, series in market.items():
        points = points_by_symbol[symbol]
        last_price = points[-1].close if points else 0.0
        symbol_trades = [trade for trade in broker.trades if trade.symbol == symbol]
        symbol_results[symbol] = {
            "source": series.source,
            "exchange_timezone": series.exchange_timezone,
            "initial_cash": round(initial_cash, 2),
            "cash": round(broker.cash, 2),
            "equity": round(final_equity, 2),
            "pnl": round(final_equity - initial_cash, 2),
            "daily_return_pct": round(((final_equity / initial_cash) - 1) * 100, 4),
            "last_price": round(last_price, 4),
            "latest_bar_time": points[-1].time if points else None,
            "latest_bar_time_et": market_time_label(points[-1].time) if points else None,
            "bars": [point.to_dict() for point in points],
            "factor_scores": factor_history.get(symbol, []),
            "trades": [trade.to_dict() for trade in symbol_trades],
            "positions": [position for position in all_positions if position["symbol"] == symbol],
            "equity_curve": [point.to_dict() for point in equity_curve],
        }

    return {
        "portfolio": {
            "initial_cash": round(initial_cash, 2),
            "cash": round(broker.cash, 2),
            "equity": round(final_equity, 2),
            "pnl": round(final_equity - initial_cash, 2),
            "daily_return_pct": round(((final_equity / initial_cash) - 1) * 100, 4),
            "total_trades": len(broker.trades),
            "positions": all_positions,
            "latest_prices": {key: round(value, 4) for key, value in latest_prices.items()},
            "latest_bar_times": {
                symbol: points[-1].time for symbol, points in points_by_symbol.items() if points
            },
            "latest_bar_times_et": {
                symbol: market_time_label(points[-1].time)
                for symbol, points in points_by_symbol.items()
                if points
            },
            "sources": {symbol: series.source for symbol, series in market.items()},
            "exchange_timezones": {
                symbol: series.exchange_timezone for symbol, series in market.items()
            },
            "market_session": market_session_info().to_dict(),
            "market_sessions": _market_sessions_payload(market),
            "report": performance_report(equity_curve, broker.trades, initial_cash=initial_cash),
        },
        "symbols": symbol_results,
        "parameters": _parameters_payload(spec.key, config, commission_rate, data_range, interval),
    }


def _parameters_payload(
    strategy_name: str,
    config: StrategyConfig,
    commission_rate: float,
    data_range: str,
    interval: str,
) -> dict[str, object]:
    spec = strategy_spec(strategy_name)
    return {
        "strategy": spec.to_dict(),
        "available_strategies": available_strategies(),
        "fast_window": config.fast_window,
        "slow_window": config.slow_window,
        "rsi_window": config.rsi_window,
        "rsi_oversold": config.rsi_oversold,
        "rsi_overbought": config.rsi_overbought,
        "bollinger_window": config.bollinger_window,
        "bollinger_stddev": config.bollinger_stddev,
        "momentum_window": config.momentum_window,
        "top_n": config.top_n,
        "range": data_range,
        "interval": interval,
        "commission_rate": commission_rate,
    }


def _top_positive_momentum(scores: dict[str, float | None]) -> str | None:
    positive_scores = {
        symbol: score
        for symbol, score in scores.items()
        if score is not None and score > 0
    }
    if not positive_scores:
        return None
    return max(positive_scores, key=positive_scores.get)


def _market_sessions_payload(market: dict[str, MarketSeries]) -> dict[str, dict[str, object]]:
    timezones = {series.exchange_timezone for series in market.values()}
    return {
        timezone: market_session_info(timezone_name=timezone).to_dict()
        for timezone in sorted(timezones)
    }


def _aggregate_symbol_equity(symbol_results: dict[str, dict[str, object]]) -> list[EquityPoint]:
    if not symbol_results:
        return []
    curves = [
        result.get("equity_curve", [])
        for result in symbol_results.values()
        if result.get("equity_curve")
    ]
    if not curves:
        return []
    length = min(len(curve) for curve in curves)
    aggregate: list[EquityPoint] = []
    for index in range(length):
        timestamp = curves[0][index]["time"]
        equity = sum(float(curve[index]["equity"]) for curve in curves)
        aggregate.append(EquityPoint(timestamp, round(equity, 2)))
    return aggregate


def _replace_signal(point: StrategyPoint, signal: str, factor_score=None) -> StrategyPoint:
    return StrategyPoint(
        time=point.time,
        time_et=point.time_et,
        time_local=point.time_local,
        timezone=point.timezone,
        open=point.open,
        high=point.high,
        low=point.low,
        close=point.close,
        volume=point.volume,
        fast_sma=point.fast_sma,
        slow_sma=point.slow_sma,
        signal=signal,
        rsi=point.rsi,
        bb_lower=point.bb_lower,
        bb_middle=point.bb_middle,
        bb_upper=point.bb_upper,
        momentum=point.momentum,
        regime=point.regime,
        factor_score=factor_score.total_score if factor_score is not None else point.factor_score,
    )
