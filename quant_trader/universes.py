"""Predefined stock universes for dashboard presets."""

from __future__ import annotations

from dataclasses import asdict, dataclass


US_TOP_100 = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "AVGO", "BRK-B",
    "LLY", "JPM", "V", "UNH", "XOM", "MA", "COST", "WMT", "NFLX", "PG",
    "JNJ", "HD", "ABBV", "BAC", "KO", "ORCL", "CRM", "MRK", "CVX", "AMD",
    "PEP", "ADBE", "TMO", "LIN", "ACN", "MCD", "CSCO", "ABT", "GE", "IBM",
    "QCOM", "TXN", "AMAT", "INTU", "DIS", "VZ", "CMCSA", "PM", "ISRG", "RTX",
    "NEE", "NOW", "UBER", "CAT", "GS", "SPGI", "PFE", "LOW", "UNP", "HON",
    "AXP", "AMGN", "BLK", "MS", "ETN", "TJX", "COP", "DE", "BKNG", "SYK",
    "MDT", "ADP", "VRTX", "ADI", "LMT", "CB", "MMC", "PLD", "REGN", "ELV",
    "BSX", "KLAC", "CI", "FI", "MDLZ", "SHOP", "PANW", "SO", "DUK", "GILD",
    "MO", "ICE", "SHW", "WM", "ZTS", "APH", "CDNS", "SNPS", "EQIX", "TT",
]


A_SHARE_CORE = [
    "600519.SS", "601318.SS", "600036.SS", "601398.SS", "601288.SS",
    "601857.SS", "600900.SS", "601088.SS", "601166.SS", "600276.SS",
    "600030.SS", "601012.SS", "600887.SS", "601668.SS", "600309.SS",
    "601899.SS", "600031.SS", "601919.SS", "600050.SS", "600028.SS",
    "600104.SS", "600406.SS", "600438.SS", "603259.SS", "603288.SS",
    "688981.SS", "688111.SS", "601888.SS", "601995.SS", "601816.SS",
    "000001.SZ", "000002.SZ", "000333.SZ", "000858.SZ", "002594.SZ",
    "300750.SZ", "000651.SZ", "002475.SZ", "002415.SZ", "300760.SZ",
    "300059.SZ", "002714.SZ", "002352.SZ", "000725.SZ", "002230.SZ",
    "002241.SZ", "000568.SZ", "300274.SZ", "300124.SZ", "300015.SZ",
]


@dataclass(frozen=True)
class UniverseSpec:
    key: str
    label: str
    description: str
    symbols: list[str]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["count"] = len(self.symbols)
        return payload


UNIVERSES = {
    "custom": UniverseSpec(
        key="custom",
        label="自定义",
        description="使用输入框中的股票代码。",
        symbols=[],
    ),
    "us_top_100": UniverseSpec(
        key="us_top_100",
        label="美股热门 Top 100",
        description="覆盖大型科技、金融、消费、医疗、工业等高关注度美股。",
        symbols=US_TOP_100,
    ),
    "a_share_core": UniverseSpec(
        key="a_share_core",
        label="A股热门核心",
        description="覆盖沪深市场中高关注度的大盘、科技、消费和金融标的。",
        symbols=A_SHARE_CORE,
    ),
}


def available_universes() -> list[dict[str, object]]:
    return [universe.to_dict() for universe in UNIVERSES.values()]


def normalize_universe(universe: str | None) -> str:
    key = (universe or "custom").strip().lower()
    if key not in UNIVERSES:
        allowed = ", ".join(UNIVERSES)
        raise ValueError(f"unknown universe '{universe}'. allowed: {allowed}")
    return key


def universe_symbols(universe: str | None) -> list[str]:
    key = normalize_universe(universe)
    return list(UNIVERSES[key].symbols)
