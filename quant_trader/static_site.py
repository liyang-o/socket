"""Generate a GitHub Pages compatible static dashboard."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any

from .market_calendar import market_session_info
from .market_data import fetch_intraday, parse_symbols
from .simulation import simulate_portfolio
from .universes import available_universes, normalize_universe, universe_symbols


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT_ROOT / "web"
DEFAULT_OUTPUT = PROJECT_ROOT / "public"


def build_static_payload(
    *,
    symbols: str,
    initial_cash: float,
    fast_window: int,
    slow_window: int,
    top_n: int,
    strategy_name: str,
    universe: str,
    commission_rate: float,
    data_range: str,
    interval: str,
) -> dict[str, Any]:
    """Build the same simulation payload used by the live API plus metadata."""

    universe_key = normalize_universe(universe)
    parsed_symbols = universe_symbols(universe_key) or parse_symbols(symbols)
    market = {
        symbol: fetch_intraday(symbol, data_range=data_range, interval=interval)
        for symbol in parsed_symbols
    }
    payload = simulate_portfolio(
        market,
        initial_cash=initial_cash,
        fast_window=fast_window,
        slow_window=slow_window,
        top_n=top_n,
        strategy_name=strategy_name,
        data_range=data_range,
        interval=interval,
        commission_rate=commission_rate,
    )
    session = market_session_info()
    payload["metadata"] = {
        "mode": "github_pages_snapshot",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_at_et": session.generated_at_et,
        "market_timezone": session.timezone,
        "symbols": parsed_symbols,
        "universe": universe_key,
        "data_range": data_range,
        "interval": interval,
    }
    payload["parameters"]["universe"] = universe_key
    payload["parameters"]["available_universes"] = available_universes()
    return payload


def generate_static_site(
    output_dir: Path = DEFAULT_OUTPUT,
    *,
    symbols: str = "AAPL,MSFT,NVDA",
    initial_cash: float = 100_000,
    fast_window: int = 12,
    slow_window: int = 26,
    top_n: int = 10,
    strategy_name: str = "sma_cross",
    universe: str = "custom",
    commission_rate: float = 0.001,
    data_range: str = "6mo",
    interval: str = "1d",
) -> Path:
    """Copy web assets and write the latest simulation JSON snapshot."""

    if output_dir.exists():
        shutil.rmtree(output_dir)
    shutil.copytree(WEB_ROOT, output_dir)

    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    payload = build_static_payload(
        symbols=symbols,
        initial_cash=initial_cash,
        fast_window=fast_window,
        slow_window=slow_window,
        top_n=top_n,
        strategy_name=strategy_name,
        universe=universe,
        commission_rate=commission_rate,
        data_range=data_range,
        interval=interval,
    )
    (data_dir / "latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a static GitHub Pages dashboard.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output directory")
    parser.add_argument("--symbols", default="AAPL,MSFT,NVDA", help="Comma-separated symbols")
    parser.add_argument("--cash", default=100_000, type=float, help="Initial paper cash")
    parser.add_argument("--fast", default=12, type=int, help="Fast SMA window")
    parser.add_argument("--slow", default=26, type=int, help="Slow SMA window")
    parser.add_argument("--top-n", default=10, type=int, help="Top N portfolio holdings")
    parser.add_argument("--strategy", default="sma_cross", help="Registered strategy key")
    parser.add_argument("--universe", default="custom", help="Universe key: custom, us_top_100, a_share_core")
    parser.add_argument("--commission", default=0.001, type=float, help="Commission rate")
    parser.add_argument("--range", default="6mo", help="Yahoo chart range")
    parser.add_argument("--interval", default="1d", help="Yahoo chart interval")
    args = parser.parse_args()

    output = generate_static_site(
        Path(args.output),
        symbols=args.symbols,
        initial_cash=args.cash,
        fast_window=args.fast,
        slow_window=args.slow,
        top_n=args.top_n,
        strategy_name=args.strategy,
        universe=args.universe,
        commission_rate=args.commission,
        data_range=args.range,
        interval=args.interval,
    )
    print(f"Generated static dashboard at {output}")


if __name__ == "__main__":
    main()
