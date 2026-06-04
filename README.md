# Quant Paper Trader

一个轻量级量化模拟交易教学项目：从公开日内行情拉取数据，运行移动均线交叉策略，使用纸面账户模拟买卖，并用网页展示当日收益、所选股票涨跌曲线、持仓和交易记录。网页支持暗色/亮色主题切换。

> 免责声明：本项目仅用于编程、量化入门和模拟交易教学，不构成投资建议，也不会向真实券商下单。

## 为什么选 SMA 交叉策略

高 star、社区认可度较高的量化/回测项目经常用双均线交叉作为第一个教学策略：

- [`kernc/backtesting.py`](https://github.com/kernc/backtesting.py)：高 star Python 回测库，官方示例包含 `SmaCross`。
- [`polakowo/vectorbt`](https://github.com/polakowo/vectorbt)：高 star 向量化量化研究框架，示例中也常用 fast/slow MA 生成交易信号。

本仓库没有直接复制这些项目的代码，而是把核心思想重构为更小、更易读的教学实现：

1. `market_data` 拉取 Yahoo Finance 日内 chart 数据，并过滤到美股常规交易时段 09:30-16:00 ET；网络不可用时用按美股交易日生成的样例行情兜底。
2. `strategy` 计算 fast/slow SMA，并在交叉时生成 `buy` / `sell` 信号。
3. `broker` 使用纸面账户模拟手续费、现金、持仓和交易记录。
4. `simulation` 聚合多只股票的当日收益。
5. `web` 用原生 SVG 画出类似 graphing calculator 的坐标网格与曲线。

## 快速开始

本项目只依赖 Python 标准库，Python 3.10+ 即可运行。

### 本地实时 API 模式

```bash
python3 -m quant_trader.server --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

如果希望强制离线演示：

```bash
QUANT_TRADER_OFFLINE=1 python3 -m quant_trader.server
```

### GitHub Pages 静态快照模式

本项目也支持 GitHub Actions + GitHub Pages。工作流会定时运行策略、生成最新模拟交易 JSON，并把纯静态网页发布到 GitHub Pages。

仓库应只保留 `.github/workflows/pages.yml` 这一条 Pages 部署 workflow；不要再启用把整个仓库根目录发布到 Pages 的旧 workflow，否则会覆盖生成好的 `public/` 站点。

1. 合并本分支后，到仓库 `Settings -> Pages`，将 Source 设置为 `GitHub Actions`。
2. 打开 `Actions -> Publish quant dashboard`，可以手动运行，也可以等待定时任务。
3. 部署完成后访问 GitHub Pages URL。

默认 workflow 每 30 分钟在美股常规交易时段附近运行一次。GitHub cron 使用 UTC，因此这里覆盖美股夏令时和冬令时的常规交易窗口；应用会在结果里标记盘前、交易中、盘后、周末和主要美股假日：

```yaml
*/30 13-21 * * 1-5
```

可通过仓库变量覆盖默认参数：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `QUANT_SYMBOLS` | `AAPL,MSFT,NVDA` | GitHub Pages 展示的股票池 |
| `QUANT_CASH` | `100000` | 初始纸面资金 |
| `QUANT_FAST` | `12` | Fast SMA 窗口 |
| `QUANT_SLOW` | `26` | Slow SMA 窗口 |

也可以本地生成同样的静态站点：

```bash
QUANT_TRADER_OFFLINE=1 python3 -m quant_trader.static_site --output public --symbols AAPL,MSFT,NVDA
```

生成结果：

```text
public/
  index.html
  app.js
  styles.css
  data/latest.json
```

> 注意：GitHub Pages 模式展示的是 Actions 最近一次生成的快照，不是浏览器关闭后仍持续运行的实时交易进程。页面会显示快照生成时间、最新行情 bar 的美东时间和美股市场状态；若需要真正持续处理新增 bar，需要部署长期运行的后端服务并持久化纸面账户状态。

## API

### 健康检查

```bash
curl http://127.0.0.1:8000/api/health
```

### 运行模拟交易

```bash
curl "http://127.0.0.1:8000/api/simulate?symbols=AAPL,MSFT,NVDA&cash=100000&fast=12&slow=26"
```

常用参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `symbols` | `AAPL,MSFT` | 逗号分隔股票代码 |
| `cash` | `100000` | 初始纸面资金 |
| `fast` | `12` | 快速 SMA 窗口 |
| `slow` | `26` | 慢速 SMA 窗口，必须大于 fast |
| `commission` | `0.001` | 单边手续费率 |
| `range` | `1d` | Yahoo chart range |
| `interval` | `1m` | Yahoo chart interval |

## 项目结构

```text
quant_trader/
  market_data.py   # 行情拉取与样例行情
  market_calendar.py # 美股交易日历、时区和常规时段
  strategy.py      # SMA 交叉信号
  broker.py        # 纸面经纪账户
  simulation.py    # 多股票组合模拟
  server.py        # HTTP API + 静态页面服务
  static_site.py   # GitHub Pages 静态站点生成
web/
  index.html
  styles.css
  app.js           # 原生 SVG 可视化
.github/workflows/
  pages.yml        # 定时生成并部署 GitHub Pages
docs/
  tutorial.md      # 教学说明
tests/
  test_strategy.py
```

## 测试

```bash
python3 -m unittest discover -s tests
```

## 后续扩展方向

- 接入正式券商 sandbox，例如 Alpaca Paper Trading 或 Interactive Brokers Paper Account。
- 增加更多策略指标，例如 RSI、布林带、动量轮动。
- 将模拟状态持久化到 SQLite，方便复盘每日交易。
- 引入 WebSocket 或 Server-Sent Events，减少轮询刷新。