# 量化模拟交易教学说明

本文用本项目的代码解释一个最小可运行量化系统如何拆分。

## 1. 行情层：`market_data.py`

`fetch_intraday(symbol)` 会优先访问 Yahoo Finance chart API：

```text
https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=1d&interval=1m
```

返回数据会被整理成统一的 `Bar`：

```python
Bar(time, open, high, low, close, volume)
```

如果网络不可用、接口限流或返回数据太少，系统会自动调用 `sample_intraday()` 生成样例数据。这保证课堂演示、CI 测试和离线环境都能正常启动。

## 2. 策略层：`strategy.py`

策略只做一件事：把价格序列转换成交易信号。

```python
fast = SMA(close, 12)
slow = SMA(close, 26)
```

信号规则：

- fast 从下方上穿 slow：`buy`
- fast 从上方下穿 slow：`sell`
- 其他情况：`hold`

这类策略的优点是简单、可解释，适合作为量化系统入门范例。缺点也很明显：震荡行情容易频繁交易，真实使用前必须做更严格的回测、风控和成本建模。

## 3. 纸面经纪账户：`broker.py`

`PaperBroker` 模拟一个 long-only 账户：

- 买入时使用当前现金的 95%。
- 支持小数股，便于教学和多价格股票对比。
- 每次交易扣除手续费。
- 卖出信号会清空对应股票持仓。

真实交易系统还需要处理：

- 滑点和盘口深度
- 部分成交
- 订单状态回报
- 熔断、停牌、涨跌停
- 风控限额和异常行情

## 4. 组合模拟：`simulation.py`

`simulate_portfolio()` 会把初始资金平均分配给所选股票，每只股票独立运行同一策略，最后聚合：

- 组合权益
- 现金余额
- 当日收益率
- 总交易次数
- 当前持仓
- 每只股票的价格曲线、交易记录和权益曲线

这种拆法使策略和交易账户彼此独立。后续要新增 RSI 策略时，不需要改行情层和网页层。

## 5. 网页可视化：`web/app.js`

前端不依赖图表库，而是使用 SVG 手写绘图：

- 网格线模拟 graphing calculator 风格。
- Close、Fast SMA、Slow SMA 分别用不同颜色显示。
- 买入/卖出点用圆点标记。
- 本地服务模式每 60 秒自动刷新一次 `/api/simulate`。
- GitHub Pages 模式每 60 秒重新读取一次 `data/latest.json` 快照。

核心思路是把数据点映射到画布坐标：

```text
x = left + index / (count - 1) * plot_width
y = top + (max_price - price) / (max_price - min_price) * plot_height
```

## 6. GitHub Pages 静态快照：`static_site.py` + Actions

GitHub Pages 不能运行 Python 后端，所以本项目增加了静态快照模式：

```text
GitHub Actions 定时运行 Python
  -> 拉取行情
  -> 运行模拟交易
  -> 生成 public/data/latest.json
  -> 部署 public/ 到 GitHub Pages
  -> 浏览器读取 latest.json 并绘图
```

本地生成方式：

```bash
python3 -m quant_trader.static_site --output public --symbols AAPL,MSFT,NVDA
```

生成后的 `public/` 是纯静态目录，可以被 GitHub Pages、Nginx、S3 静态网站等直接托管。

`.github/workflows/pages.yml` 做了三件事：

1. 定时或手动触发 workflow。
2. 执行 `python3 -m quant_trader.static_site` 生成站点。
3. 使用 `actions/deploy-pages` 发布到 GitHub Pages。

重要限制：

- Pages 展示的是最近一次 workflow 生成的快照，不是毫秒级实时流。
- 修改股票池和参数需要重新运行 workflow，或配置仓库变量 `QUANT_SYMBOLS`、`QUANT_CASH`、`QUANT_FAST`、`QUANT_SLOW`。
- 如果 GitHub Actions 运行时行情接口不可用，仍会使用样例行情兜底，页面会显示数据来源。

## 7. 如何运行

```bash
python3 -m quant_trader.server --host 127.0.0.1 --port 8000
```

访问：

```text
http://127.0.0.1:8000
```

离线模式：

```bash
QUANT_TRADER_OFFLINE=1 python3 -m quant_trader.server
```

运行测试：

```bash
python3 -m unittest discover -s tests
```

## 8. 接入真实券商前必须补齐的内容

本项目当前只做模拟交易，不会真实下单。若要接入真实券商或 sandbox，请先补齐：

1. API key 管理：使用环境变量或密钥管理服务，不要提交到 git。
2. 订单适配器：把 `PaperBroker.buy/sell_all` 替换为券商 sandbox 的 order API。
3. 风控层：最大仓位、最大亏损、交易时间窗口、异常价格过滤。
4. 审计日志：保存每次信号、下单请求、订单回报和账户快照。
5. 灾备开关：出现异常时能一键停止策略并撤单。
