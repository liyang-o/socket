"""Backtest report metrics."""

from __future__ import annotations

import math

from .broker import EquityPoint, Trade


def performance_report(
    equity_curve: list[EquityPoint],
    trades: list[Trade],
    *,
    initial_cash: float,
) -> dict[str, float | int]:
    """Compute compact strategy diagnostics."""

    if not equity_curve or initial_cash <= 0:
        return {
            "total_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe": 0.0,
            "volatility_pct": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "trade_count": len(trades),
        }

    equities = [point.equity for point in equity_curve]
    returns = [
        (equities[index] / equities[index - 1]) - 1
        for index in range(1, len(equities))
        if equities[index - 1] > 0
    ]
    final_equity = equities[-1]
    total_return_pct = ((final_equity / initial_cash) - 1) * 100
    volatility = _stdev(returns) * math.sqrt(252) * 100 if returns else 0.0
    sharpe = (_mean(returns) / _stdev(returns) * math.sqrt(252)) if _stdev(returns) else 0.0
    wins, losses = _trade_pnls(trades)
    gross_profit = sum(value for value in wins if value > 0)
    gross_loss = abs(sum(value for value in losses if value < 0))
    profit_factor = gross_profit / gross_loss if gross_loss else 0.0
    completed_trades = len(wins) + len(losses)
    win_rate = (len(wins) / completed_trades * 100) if completed_trades else 0.0

    return {
        "total_return_pct": round(total_return_pct, 4),
        "max_drawdown_pct": round(_max_drawdown(equities), 4),
        "sharpe": round(sharpe, 4),
        "volatility_pct": round(volatility, 4),
        "win_rate_pct": round(win_rate, 4),
        "profit_factor": round(profit_factor, 4),
        "trade_count": len(trades),
    }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def _max_drawdown(equities: list[float]) -> float:
    peak = equities[0]
    max_drawdown = 0.0
    for equity in equities:
        peak = max(peak, equity)
        if peak:
            max_drawdown = min(max_drawdown, (equity / peak - 1) * 100)
    return max_drawdown


def _trade_pnls(trades: list[Trade]) -> tuple[list[float], list[float]]:
    open_prices: dict[str, list[tuple[float, float]]] = {}
    wins: list[float] = []
    losses: list[float] = []
    for trade in trades:
        if trade.side == "buy":
            open_prices.setdefault(trade.symbol, []).append((trade.price, trade.quantity))
            continue
        lots = open_prices.get(trade.symbol, [])
        if not lots:
            continue
        entry_price, quantity = lots.pop(0)
        pnl = (trade.price - entry_price) * min(quantity, trade.quantity) - trade.commission
        if pnl >= 0:
            wins.append(pnl)
        else:
            losses.append(pnl)
    return wins, losses
