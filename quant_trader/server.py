"""HTTP API and static web server for the quant paper trader."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .market_data import fetch_intraday, parse_symbols
from .simulation import simulate_portfolio


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT_ROOT / "web"


class QuantTraderHandler(SimpleHTTPRequestHandler):
    """Serve the dashboard and JSON API from one lightweight process."""

    server_version = "QuantPaperTrader/0.1"

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._send_json({"ok": True, "service": "quant-paper-trader"})
            return
        if parsed.path == "/api/simulate":
            self._handle_simulate(parsed.query)
            return
        self._serve_static(parsed.path)

    def _handle_simulate(self, query: str) -> None:
        params = parse_qs(query)
        try:
            symbols = parse_symbols(_first(params, "symbols", "AAPL,MSFT"))
            fast_window = _int_param(params, "fast", 12)
            slow_window = _int_param(params, "slow", 26)
            initial_cash = _float_param(params, "cash", 100_000)
            commission_rate = _float_param(params, "commission", 0.001)
            data_range = _first(params, "range", "1d")
            interval = _first(params, "interval", "1m")

            market = {
                symbol: fetch_intraday(symbol, data_range=data_range, interval=interval)
                for symbol in symbols
            }
            result = simulate_portfolio(
                market,
                initial_cash=initial_cash,
                fast_window=fast_window,
                slow_window=slow_window,
                commission_rate=commission_rate,
            )
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        self._send_json(result)

    def _serve_static(self, path: str) -> None:
        if path in ("", "/"):
            target = WEB_ROOT / "index.html"
        else:
            target = (WEB_ROOT / path.lstrip("/")).resolve()
            if WEB_ROOT not in target.parents and target != WEB_ROOT:
                self._send_json({"error": "invalid path"}, status=HTTPStatus.FORBIDDEN)
                return

        if not target.is_file():
            self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return

        content = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", _content_type(target))
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        """Keep request logs concise."""

        print(f"{self.address_string()} - {format % args}")


def _first(params: dict[str, list[str]], name: str, default: str) -> str:
    values = params.get(name)
    return values[0] if values and values[0] else default


def _int_param(params: dict[str, list[str]], name: str, default: int) -> int:
    value = int(_first(params, name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _float_param(params: dict[str, list[str]], name: str, default: float) -> float:
    value = float(_first(params, name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".svg": "image/svg+xml",
    }.get(suffix, "application/octet-stream")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the quant paper trading dashboard.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", default=8000, type=int, help="Bind port")
    args = parser.parse_args()

    httpd = ThreadingHTTPServer((args.host, args.port), QuantTraderHandler)
    print(f"Quant paper trader running at http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
