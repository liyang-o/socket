const state = {
  data: null,
  mode: null,
  selectedSymbol: null,
  timer: null,
};

const STATIC_DATA_URL = "data/latest.json";
const THEME_KEY = "quant-paper-theme";

const els = {
  symbolsInput: document.querySelector("#symbolsInput"),
  cashInput: document.querySelector("#cashInput"),
  strategyInput: document.querySelector("#strategyInput"),
  rangeInput: document.querySelector("#rangeInput"),
  intervalInput: document.querySelector("#intervalInput"),
  fastInput: document.querySelector("#fastInput"),
  slowInput: document.querySelector("#slowInput"),
  runButton: document.querySelector("#runButton"),
  themeToggle: document.querySelector("#themeToggle"),
  autoRefresh: document.querySelector("#autoRefresh"),
  symbolSelect: document.querySelector("#symbolSelect"),
  equityMetric: document.querySelector("#equityMetric"),
  returnMetric: document.querySelector("#returnMetric"),
  pnlMetric: document.querySelector("#pnlMetric"),
  tradesMetric: document.querySelector("#tradesMetric"),
  sourceBadge: document.querySelector("#sourceBadge"),
  updatedAt: document.querySelector("#updatedAt"),
  marketMeta: document.querySelector("#marketMeta"),
  latestBarMeta: document.querySelector("#latestBarMeta"),
  priceChart: document.querySelector("#priceChart"),
  equityChart: document.querySelector("#equityChart"),
  positionsTable: document.querySelector("#positionsTable"),
  tradesTable: document.querySelector("#tradesTable"),
  errorBox: document.querySelector("#errorBox"),
};

initTheme();

els.runButton.addEventListener("click", () => runSimulation());
els.themeToggle.addEventListener("click", toggleTheme);
els.symbolSelect.addEventListener("change", () => {
  state.selectedSymbol = els.symbolSelect.value;
  render();
});
els.autoRefresh.addEventListener("change", scheduleRefresh);

runSimulation();
scheduleRefresh();

function scheduleRefresh() {
  if (state.timer) {
    clearInterval(state.timer);
    state.timer = null;
  }
  if (els.autoRefresh.checked) {
    state.timer = setInterval(() => runSimulation({ silent: true }), 60_000);
  }
}

function initTheme() {
  const savedTheme = localStorage.getItem(THEME_KEY);
  const prefersLight = window.matchMedia?.("(prefers-color-scheme: light)").matches;
  applyTheme(savedTheme || (prefersLight ? "light" : "dark"));
}

function toggleTheme() {
  const current = document.documentElement.dataset.theme === "light" ? "light" : "dark";
  applyTheme(current === "light" ? "dark" : "light");
}

function applyTheme(theme) {
  const normalized = theme === "light" ? "light" : "dark";
  document.documentElement.dataset.theme = normalized;
  localStorage.setItem(THEME_KEY, normalized);

  const isLight = normalized === "light";
  els.themeToggle.textContent = isLight ? "暗色模式" : "亮色模式";
  els.themeToggle.setAttribute("aria-label", isLight ? "切换暗色主题" : "切换亮色主题");
}

async function runSimulation(options = {}) {
  setLoading(true, options.silent);
  hideError();

  const params = new URLSearchParams({
    symbols: els.symbolsInput.value,
    strategy: els.strategyInput.value,
    range: els.rangeInput.value,
    interval: els.intervalInput.value,
    cash: els.cashInput.value,
    fast: els.fastInput.value,
    slow: els.slowInput.value,
  });

  try {
    const { payload, mode } = await loadSimulation(params);
    state.data = payload;
    state.mode = mode;
    syncControlsFromPayload(payload, mode);
    const symbols = Object.keys(payload.symbols);
    if (!symbols.includes(state.selectedSymbol)) {
      state.selectedSymbol = symbols[0];
    }
    render();
  } catch (error) {
    showError(error.message);
  } finally {
    setLoading(false);
  }
}

async function loadSimulation(params) {
  if (isGitHubPages()) {
    return { payload: await fetchStaticSnapshot(), mode: "static" };
  }

  try {
    return { payload: await fetchApiSimulation(params), mode: "api" };
  } catch (apiError) {
    const payload = await fetchStaticSnapshot();
    payload.metadata = {
      ...(payload.metadata || {}),
      api_error: apiError.message,
    };
    return { payload, mode: "static" };
  }
}

async function fetchApiSimulation(params) {
  const response = await fetch(`/api/simulate?${params.toString()}`);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "请求失败");
  }
  return payload;
}

async function fetchStaticSnapshot() {
  const response = await fetch(`${STATIC_DATA_URL}?t=${Date.now()}`);
  if (!response.ok) {
    throw new Error("无法加载静态快照 data/latest.json");
  }
  return response.json();
}

function isGitHubPages() {
  return window.location.hostname.endsWith("github.io");
}

function syncControlsFromPayload(payload, mode) {
  const symbols = Object.keys(payload.symbols);
  const parameters = payload.parameters || {};
  if (mode === "static") {
    els.symbolsInput.value = symbols.join(",");
    els.strategyInput.value = parameters.strategy?.key || els.strategyInput.value;
    els.rangeInput.value = parameters.range || els.rangeInput.value;
    els.intervalInput.value = parameters.interval || els.intervalInput.value;
    els.cashInput.value = payload.portfolio.initial_cash;
    els.fastInput.value = parameters.fast_window || els.fastInput.value;
    els.slowInput.value = parameters.slow_window || els.slowInput.value;
  }

  const isStatic = mode === "static";
  for (const input of [
    els.symbolsInput,
    els.strategyInput,
    els.rangeInput,
    els.intervalInput,
    els.cashInput,
    els.fastInput,
    els.slowInput,
  ]) {
    input.disabled = isStatic;
    input.title = isStatic ? "GitHub Pages 静态模式下参数由 Actions 工作流生成" : "";
  }
}

function render() {
  if (!state.data) return;

  renderMetrics(state.data.portfolio);
  renderStrategyOptions(state.data.parameters?.available_strategies || []);
  renderSymbolOptions(Object.keys(state.data.symbols));

  const selected = state.data.symbols[state.selectedSymbol];
  const sources = Object.values(state.data.portfolio.sources);
  const dataSourceText = sources.every((source) => source === "yahoo")
    ? "Yahoo Finance"
    : "样例行情兜底";
  const sourceText = state.mode === "static"
    ? `GitHub Pages 快照 · ${dataSourceText}`
    : dataSourceText;
  els.sourceBadge.textContent = sourceText;
  renderMarketTime(selected);

  renderPriceChart(selected.bars, selected.trades);
  renderEquityChart(selected.equity_curve);
  renderPositionsTable(state.data.portfolio.positions);
  renderTradesTable(selected.trades);
}

function renderMarketTime(selected) {
  const session = state.data.portfolio.market_session || {};
  const timezone = selectedTimezone(selected);
  const latestBar = selected.bars.at(-1)?.time_local || selected.latest_bar_time_et || "--";
  const currentExchangeTime = exchangeDateTimeLabel(new Date(), timezone);
  const modeText = state.mode === "static" ? "快照生成" : "本地刷新";
  const updatedAt = state.mode === "static"
    ? state.data.metadata?.generated_at_et || dateTimeLabel(state.data.metadata?.generated_at)
    : exchangeDateTimeLabel(new Date(), timezone);
  const range = state.data.parameters?.range || els.rangeInput.value;
  const interval = state.data.parameters?.interval || els.intervalInput.value;
  const statusText = timezone === session.timezone
    ? marketStatusText(session)
    : "未接入该交易所日历";

  els.updatedAt.textContent = `${modeText}: ${updatedAt}`;
  els.marketMeta.textContent = `交易状态: ${statusText} · 当前实际时间: ${currentExchangeTime}`;
  els.latestBarMeta.textContent = `策略: ${strategyLabel()} · 数据: ${range}/${interval} · 最新 bar: ${latestBar}`;
}

function marketStatusText(session) {
  const statusMap = {
    open: "常规交易中",
    pre_market: "盘前，常规交易未开",
    after_hours: "盘后，常规交易已收",
    closed: "休市",
  };
  const status = statusMap[session.status] || "未知";
  const close = session.close_time_et ? `，收盘 ${session.close_time_et}` : "";
  return `${status}${close}`;
}

function selectedTimezone(selected = null) {
  const symbol = state.selectedSymbol;
  return (
    selected?.exchange_timezone ||
    selected?.bars?.at(-1)?.timezone ||
    state.data?.portfolio?.exchange_timezones?.[symbol] ||
    state.data?.portfolio?.market_session?.timezone ||
    "America/New_York"
  );
}

function strategyLabel() {
  return state.data.parameters?.strategy?.label || "SMA 双均线趋势";
}

function renderMetrics(portfolio) {
  els.equityMetric.textContent = money(portfolio.equity);
  els.returnMetric.textContent = `${portfolio.daily_return_pct.toFixed(2)}%`;
  els.pnlMetric.textContent = money(portfolio.pnl);
  els.tradesMetric.textContent = portfolio.total_trades;

  setTone(els.returnMetric, portfolio.daily_return_pct);
  setTone(els.pnlMetric, portfolio.pnl);
}

function renderSymbolOptions(symbols) {
  els.symbolSelect.innerHTML = "";
  for (const symbol of symbols) {
    const option = document.createElement("option");
    option.value = symbol;
    option.textContent = symbol;
    option.selected = symbol === state.selectedSymbol;
    els.symbolSelect.append(option);
  }
}

function renderStrategyOptions(strategies) {
  if (!strategies.length) return;

  const selected = state.data.parameters?.strategy?.key || els.strategyInput.value;
  els.strategyInput.innerHTML = "";
  for (const strategy of strategies) {
    const option = document.createElement("option");
    option.value = strategy.key;
    option.textContent = strategy.label;
    option.selected = strategy.key === selected;
    option.title = strategy.description;
    els.strategyInput.append(option);
  }
}

function renderPriceChart(points, trades) {
  if (!points.length) {
    els.priceChart.innerHTML = '<p class="empty">没有行情数据</p>';
    return;
  }

  const values = points.flatMap((point) =>
    [
      point.close,
      point.fast_sma,
      point.slow_sma,
      point.bb_lower,
      point.bb_middle,
      point.bb_upper,
    ].filter((value) => value !== null && value !== undefined),
  );
  const scale = makeScale(points.length, values, 760, 330);
  const svg = baseSvg(scale.width, scale.height);

  drawGrid(svg, scale);
  const legend = [["Close", "#9be7ff"]];
  drawLine(svg, points.map((point) => point.close), scale, "#9be7ff", 3);
  if (hasSeries(points, "fast_sma")) {
    drawLine(svg, points.map((point) => point.fast_sma), scale, "#2ee59d", 1.8);
    legend.push(["Fast SMA", "#2ee59d"]);
  }
  if (hasSeries(points, "slow_sma")) {
    drawLine(svg, points.map((point) => point.slow_sma), scale, "#ffd166", 1.8);
    legend.push(["Slow SMA", "#ffd166"]);
  }
  if (hasSeries(points, "bb_upper")) {
    drawLine(svg, points.map((point) => point.bb_upper), scale, "#8a7dff", 1.3);
    drawLine(svg, points.map((point) => point.bb_middle), scale, "#ffd166", 1.2);
    drawLine(svg, points.map((point) => point.bb_lower), scale, "#8a7dff", 1.3);
    legend.push(["Bollinger", "#8a7dff"]);
  }
  drawTradeMarkers(svg, points, trades, scale);
  legend.push(["Buy/Sell", "#ff6b7a"]);
  drawLegend(svg, legend);

  els.priceChart.replaceChildren(svg);
}

function hasSeries(points, key) {
  return points.some((point) => point[key] !== null && point[key] !== undefined);
}

function renderEquityChart(points) {
  if (!points.length) {
    els.equityChart.innerHTML = '<p class="empty">没有权益数据</p>';
    return;
  }

  const values = points.map((point) => point.equity);
  const scale = makeScale(points.length, values, 560, 330);
  const svg = baseSvg(scale.width, scale.height);
  drawGrid(svg, scale, (value) => money(value));
  drawLine(svg, values, scale, "#6fb6ff", 3);
  drawLegend(svg, [["Equity", "#6fb6ff"]]);
  els.equityChart.replaceChildren(svg);
}

function renderPositionsTable(positions) {
  if (!positions.length) {
    els.positionsTable.innerHTML = '<p class="empty">当前没有持仓</p>';
    return;
  }

  els.positionsTable.innerHTML = table(
    ["股票", "数量", "均价", "最新价", "市值", "浮动盈亏"],
    positions.map((row) => [
      row.symbol,
      row.quantity.toFixed(4),
      money(row.average_price),
      money(row.last_price),
      money(row.market_value),
      toneText(row.unrealized_pnl, money(row.unrealized_pnl)),
    ]),
  );
}

function renderTradesTable(trades) {
  if (!trades.length) {
    els.tradesTable.innerHTML = '<p class="empty">所选股票暂无交易</p>';
    return;
  }

  els.tradesTable.innerHTML = table(
    ["时间", "方向", "价格", "数量", "手续费", "剩余现金"],
    trades
      .slice()
      .reverse()
      .map((trade) => [
        timeLabel(trade.time),
        trade.side === "buy" ? "买入" : "卖出",
        money(trade.price),
        trade.quantity.toFixed(4),
        money(trade.commission),
        money(trade.cash_after),
      ]),
  );
}

function makeScale(count, values, width, height) {
  const padding = { top: 26, right: 24, bottom: 34, left: 62 };
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const spread = Math.max(maxValue - minValue, Math.abs(maxValue) * 0.01, 1);
  const min = minValue - spread * 0.08;
  const max = maxValue + spread * 0.08;
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;

  return {
    width,
    height,
    padding,
    min,
    max,
    x: (index) => padding.left + (plotWidth * index) / Math.max(count - 1, 1),
    y: (value) => padding.top + ((max - value) / (max - min)) * plotHeight,
  };
}

function baseSvg(width, height) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("role", "img");
  return svg;
}

function drawGrid(svg, scale, labelFormatter = compactNumber) {
  const { width, height, padding } = scale;
  const grid = document.createElementNS(svg.namespaceURI, "g");
  grid.setAttribute("stroke", "rgba(147, 164, 196, 0.18)");
  grid.setAttribute("stroke-width", "1");

  for (let index = 0; index <= 4; index += 1) {
    const y = padding.top + ((height - padding.top - padding.bottom) * index) / 4;
    grid.append(line(padding.left, y, width - padding.right, y));

    const value = scale.max - ((scale.max - scale.min) * index) / 4;
    const label = text(8, y + 4, labelFormatter(value));
    label.setAttribute("class", "axis-label");
    svg.append(label);
  }

  for (let index = 0; index <= 6; index += 1) {
    const x = padding.left + ((width - padding.left - padding.right) * index) / 6;
    grid.append(line(x, padding.top, x, height - padding.bottom));
  }
  svg.prepend(grid);
}

function drawLine(svg, values, scale, color, width) {
  const segments = [];
  let current = [];

  values.forEach((value, index) => {
    if (value === null || Number.isNaN(value)) {
      if (current.length) segments.push(current);
      current = [];
      return;
    }
    current.push([scale.x(index), scale.y(value)]);
  });
  if (current.length) segments.push(current);

  for (const segment of segments) {
    if (segment.length < 2) continue;
    const path = document.createElementNS(svg.namespaceURI, "path");
    path.setAttribute("d", segment.map(([x, y], index) => `${index ? "L" : "M"} ${x} ${y}`).join(" "));
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", color);
    path.setAttribute("stroke-width", width);
    path.setAttribute("stroke-linecap", "round");
    path.setAttribute("stroke-linejoin", "round");
    svg.append(path);
  }
}

function drawTradeMarkers(svg, points, trades, scale) {
  const tradeByTime = new Map(trades.map((trade) => [trade.time, trade]));
  points.forEach((point, index) => {
    const trade = tradeByTime.get(point.time);
    if (!trade) return;

    const marker = document.createElementNS(svg.namespaceURI, "circle");
    marker.setAttribute("cx", scale.x(index));
    marker.setAttribute("cy", scale.y(point.close));
    marker.setAttribute("r", "5.5");
    marker.setAttribute("fill", trade.side === "buy" ? "#2ee59d" : "#ff6b7a");
    marker.setAttribute("stroke", "#07101f");
    marker.setAttribute("stroke-width", "2");
    svg.append(marker);
  });
}

function drawLegend(svg, entries) {
  const group = document.createElementNS(svg.namespaceURI, "g");
  entries.forEach(([label, color], index) => {
    const x = 70 + index * 112;
    const y = 18;
    const dot = document.createElementNS(svg.namespaceURI, "circle");
    dot.setAttribute("cx", x);
    dot.setAttribute("cy", y - 4);
    dot.setAttribute("r", "4");
    dot.setAttribute("fill", color);
    group.append(dot);

    const labelNode = text(x + 10, y, label);
    labelNode.setAttribute("class", "axis-label");
    group.append(labelNode);
  });
  svg.append(group);
}

function line(x1, y1, x2, y2) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", "line");
  node.setAttribute("x1", x1);
  node.setAttribute("y1", y1);
  node.setAttribute("x2", x2);
  node.setAttribute("y2", y2);
  return node;
}

function text(x, y, value) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", "text");
  node.setAttribute("x", x);
  node.setAttribute("y", y);
  node.textContent = value;
  return node;
}

function table(headers, rows) {
  return `
    <table>
      <thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>
      <tbody>
        ${rows
          .map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`)
          .join("")}
      </tbody>
    </table>
  `;
}

function toneText(value, content) {
  const className = value >= 0 ? "positive" : "negative";
  return `<span class="${className}">${escapeHtml(content)}</span>`;
}

function money(value) {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function compactNumber(value) {
  return new Intl.NumberFormat("zh-CN", {
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(value);
}

function timeLabel(value) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: selectedTimezone(),
    timeZoneName: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function dateTimeLabel(value) {
  if (!value) return "--";
  return new Date(value).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function etDateTimeLabel(value) {
  return exchangeDateTimeLabel(value, "America/New_York");
}

function exchangeDateTimeLabel(value, timezone) {
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: timezone || "America/New_York",
    timeZoneName: "short",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(value);
  return parts;
}

function setTone(element, value) {
  element.classList.toggle("positive", value >= 0);
  element.classList.toggle("negative", value < 0);
}

function setLoading(isLoading, silent = false) {
  els.runButton.disabled = isLoading;
  if (!silent) {
    els.runButton.textContent = isLoading ? "加载中..." : runButtonLabel();
  } else if (!isLoading) {
    els.runButton.textContent = runButtonLabel();
  }
}

function runButtonLabel() {
  return state.mode === "static" ? "刷新快照" : "运行模拟";
}

function showError(message) {
  els.errorBox.hidden = false;
  els.errorBox.textContent = message;
}

function hideError() {
  els.errorBox.hidden = true;
  els.errorBox.textContent = "";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
