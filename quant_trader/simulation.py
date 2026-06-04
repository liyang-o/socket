"""Run strategy signals through the paper broker."""

from __future__ import annotations

from .broker import EquityPoint, PaperBroker
from .market_calendar import market_session_info, market_time_label
from .market_data import MarketSeries
from .strategy import StrategyPoint, sma_crossover_signals


def simulate_portfolio(
    market: dict[str, MarketSeries],
    *,
    initial_cash: float = 100_000,
    fast_window: int = 12,
    slow_window: int = 26,
    commission_rate: float = 0.001,
) -> dict[str, object]:
    """Simulate each selected symbol, then aggregate the resulting account."""

    if initial_cash <= 0:
        raise ValueError("initial_cash must be greater than zero")
    if not market:
        raise ValueError("market data cannot be empty")

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

    for symbol, series in market.items():
        broker = PaperBroker(cash=allocation, commission_rate=commission_rate)
        points = sma_crossover_signals(series.bars, fast_window, slow_window)
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
        all_positions.extend(broker.open_positions({symbol: last_price}))

        symbol_results[symbol] = {
            "source": series.source,
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
            "market_session": market_session_info().to_dict(),
        },
        "symbols": symbol_results,
        "parameters": {
            "fast_window": fast_window,
            "slow_window": slow_window,
            "commission_rate": commission_rate,
        },
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
