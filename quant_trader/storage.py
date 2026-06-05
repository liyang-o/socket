"""SQLite storage for historical market bars."""

from __future__ import annotations

from pathlib import Path
import os
import sqlite3
from typing import Iterable

from .market_data import Bar


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "market_cache.sqlite"


class SQLiteBarStore:
    """Small dependency-free bar cache used by API and Pages generation."""

    def __init__(self, path: Path | str | None = None) -> None:
        configured = path or os.getenv("QUANT_TRADER_DB")
        self.path = Path(configured) if configured else DEFAULT_DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def save_bars(
        self,
        symbol: str,
        bars: Iterable[Bar],
        *,
        source: str,
        exchange_timezone: str,
        data_range: str,
        interval: str,
    ) -> int:
        rows = [
            (
                symbol,
                bar.time,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                bar.time_et,
                bar.time_local,
                bar.timezone,
                source,
                exchange_timezone,
                data_range,
                interval,
            )
            for bar in bars
        ]
        if not rows:
            return 0

        with sqlite3.connect(self.path) as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO bars (
                    symbol, time, open, high, low, close, volume,
                    time_et, time_local, timezone, source,
                    exchange_timezone, data_range, interval
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def load_bars(self, symbol: str, *, data_range: str, interval: str) -> list[Bar]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                """
                SELECT time, open, high, low, close, volume, time_et, time_local, timezone
                FROM bars
                WHERE symbol = ? AND data_range = ? AND interval = ?
                ORDER BY time ASC
                """,
                (symbol, data_range, interval),
            ).fetchall()

        return [
            Bar(
                time=row[0],
                open=row[1],
                high=row[2],
                low=row[3],
                close=row[4],
                volume=row[5],
                time_et=row[6],
                time_local=row[7],
                timezone=row[8],
            )
            for row in rows
        ]

    def _init_schema(self) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS bars (
                    symbol TEXT NOT NULL,
                    time TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume INTEGER NOT NULL,
                    time_et TEXT NOT NULL,
                    time_local TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    source TEXT NOT NULL,
                    exchange_timezone TEXT NOT NULL,
                    data_range TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    PRIMARY KEY (symbol, time, data_range, interval)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_bars_symbol_range_interval
                ON bars(symbol, data_range, interval, time)
                """
            )


def default_store() -> SQLiteBarStore:
    return SQLiteBarStore()
