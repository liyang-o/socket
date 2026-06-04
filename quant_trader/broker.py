"""Paper broker primitives for simulated trading."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Position:
    """Current holdings for one symbol."""

    symbol: str
    quantity: float = 0.0
    average_price: float = 0.0

    def market_value(self, price: float) -> float:
        return self.quantity * price

    def unrealized_pnl(self, price: float) -> float:
        return (price - self.average_price) * self.quantity


@dataclass(frozen=True)
class Trade:
    """A simulated order fill."""

    time: str
    symbol: str
    side: str
    price: float
    quantity: float
    commission: float
    cash_after: float

    def to_dict(self) -> dict[str, float | str]:
        return asdict(self)


@dataclass(frozen=True)
class EquityPoint:
    """Portfolio value at one point in time."""

    time: str
    equity: float

    def to_dict(self) -> dict[str, float | str]:
        return asdict(self)


@dataclass
class PaperBroker:
    """A small long-only broker simulator with fractional shares."""

    cash: float
    commission_rate: float = 0.001
    trade_fraction: float = 0.95
    positions: dict[str, Position] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)

    def buy(self, symbol: str, price: float, time: str) -> Trade | None:
        if price <= 0 or self.cash <= 0:
            return None

        budget = self.cash * self.trade_fraction
        quantity = budget / (price * (1 + self.commission_rate))
        if quantity <= 0:
            return None

        gross = quantity * price
        commission = gross * self.commission_rate
        self.cash -= gross + commission

        position = self.positions.setdefault(symbol, Position(symbol=symbol))
        new_quantity = position.quantity + quantity
        position.average_price = (
            (position.average_price * position.quantity + gross) / new_quantity
            if new_quantity
            else 0.0
        )
        position.quantity = new_quantity

        trade = Trade(time, symbol, "buy", price, quantity, commission, self.cash)
        self.trades.append(trade)
        return trade

    def sell_all(self, symbol: str, price: float, time: str) -> Trade | None:
        position = self.positions.get(symbol)
        if position is None or position.quantity <= 0 or price <= 0:
            return None

        quantity = position.quantity
        gross = quantity * price
        commission = gross * self.commission_rate
        self.cash += gross - commission

        position.quantity = 0.0
        position.average_price = 0.0

        trade = Trade(time, symbol, "sell", price, quantity, commission, self.cash)
        self.trades.append(trade)
        return trade

    def equity(self, prices: dict[str, float]) -> float:
        value = self.cash
        for symbol, position in self.positions.items():
            value += position.market_value(prices.get(symbol, position.average_price))
        return value

    def open_positions(self, prices: dict[str, float]) -> list[dict[str, float | str]]:
        rows: list[dict[str, float | str]] = []
        for symbol, position in self.positions.items():
            if position.quantity <= 0:
                continue
            price = prices.get(symbol, position.average_price)
            rows.append(
                {
                    "symbol": symbol,
                    "quantity": round(position.quantity, 6),
                    "average_price": round(position.average_price, 4),
                    "last_price": round(price, 4),
                    "market_value": round(position.market_value(price), 2),
                    "unrealized_pnl": round(position.unrealized_pnl(price), 2),
                }
            )
        return rows
