# Quant Paper Trader

一个轻量级量化模拟交易教学项目：从公开日内行情拉取数据，运行可扩展策略池，使用纸面账户模拟买卖，并用网页展示当日收益、所选股票涨跌曲线、持仓和交易记录。网页支持暗色/亮色主题切换。

> 免责声明：本项目仅用于编程、量化入门和模拟交易教学，不构成投资建议，也不会向真实券商下单。

## 策略设计

近期量化实践更强调“策略池 + regime/risk layer”，而不是押注单一指标。趋势市常用动量/均线，震荡市常用 RSI、布林带等均值回归，组合层再用相对强弱做轮动。本项目先实现一组无外部依赖、适合教学和扩展的策略：

| 策略 key | 名称 | 类型 | 适用场景 |
| --- | --- | --- | --- |
| `sma_cross` | SMA 双均线趋势 | 趋势跟随 | 趋势明确时，fast SMA 上穿/下穿 slow SMA |
| `rsi_reversion` | RSI 均值回归 | 均值回归 | 短周期超卖修复/超买退出 |
| `bollinger_reversion` | 布林带均值回归 | 均值回归 | 区间震荡，价格偏离下轨后回归中轨 |
| `hybrid_reversion` | RSI + 布林带混合 | 混合 | 同时用动量强弱和波动带过滤假信号 |
| `momentum_rotation` | 多资产动量轮动 | 组合级 | 在多只股票中持有正动量最强标的 |
| `dual_momentum` | 双动量轮动 | 组合级 | 先要求绝对动量为正，再选择相对动量最强标的 |
| `trend_pullback` | 趋势过滤回调 | 混合 | 只在长期趋势向上时寻找 RSI/布林带短期回调 |
| `regime_adaptive` | Regime 自适应 | 混合 | 在趋势、震荡均值回归和风险规避之间切换 |
| `multi_factor_top` | 多因子 Top N | 组合级 | 综合动量、反转、低波、流动性和趋势因子，选择 Top N 并波动率加权 |

## 机构化框架第一版

本仓库新增了面向私募量化框架的第一版基础设施：

- `storage.py`：SQLite 行情缓存。在线数据成功拉取后写入 `data/market_cache.sqlite`；在线失败时优先读取缓存，再退回样例数据。
- `factors.py`：多因子打分。当前包含 60/120 日动量、20 日短期反转、低波动、流动性趋势和长期趋势过滤。
- `multi_factor_top`：组合级多因子策略。横截面标准化后合成总分，选择正分 Top N，并用波动率倒数加权。
- `metrics.py`：回测指标报告。返回总收益、最大回撤、Sharpe、波动率、胜率、Profit Factor、交易次数。
- 风控雏形：多因子组合默认保留现金缓冲、单票权重上限、弱信号空仓，后续可扩展最大回撤熔断、换手率限制、行业约束和交易成本模型。

这不是收益承诺，而是为了让系统具备未来实盘研究必需的结构：历史数据、因子、组合、风控、报告和复盘。

## 股票池和市场支持

内置股票池：

| universe key | 名称 | 说明 |
| --- | --- | --- |
| `custom` | 自定义 | 使用输入框中的股票代码 |
| `us_top_100` | 美股热门 Top 100 | 覆盖大型科技、金融、消费、医疗、工业等高关注度美股 |
| `a_share_core` | A股热门核心 | 覆盖沪深市场中高关注度的大盘、科技、消费和金融标的 |

A 股通过 Yahoo Finance 代码访问：

- `600519` / `sh600519` 会自动映射为 `600519.SS`
- `000001` / `sz000001` 会自动映射为 `000001.SZ`
- 也可以直接输入 `600519.SS,000001.SZ`

交易时间显示：

- 美股使用 `America/New_York`，常规时段 `09:30-16:00`。
- A 股使用 `Asia/Shanghai`，常规时段 `09:30-11:30`、`13:00-15:00`。
- 页面会根据所选股票的交易所时区显示当前实际时间和是否处于交易时段。

> A 股当前支持常规交易时段和周末识别；法定节假日、调休交易日建议后续接入官方交易日历源。

高 star、社区认可度较高的量化/回测项目经常用双均线交叉作为第一个教学策略：

- [`kernc/backtesting.py`](https://github.com/kernc/backtesting.py)：高 star Python 回测库，官方示例包含 `SmaCross`。
- [`polakowo/vectorbt`](https://github.com/polakowo/vectorbt)：高 star 向量化量化研究框架，示例中也常用 fast/slow MA 生成交易信号。

本仓库没有直接复制这些项目的代码，而是把核心思想重构为更小、更易读的教学实现：

1. `market_data` 拉取 Yahoo Finance 日内 chart 数据，并过滤到美股常规交易时段 09:30-16:00 ET；网络不可用时用按美股交易日生成的样例行情兜底。
2. `indicators` 复用 SMA、RSI、布林带、动量等指标。
3. `strategy` 通过注册表管理策略，生成 `buy` / `sell` / `hold` 信号。
4. `broker` 使用纸面账户模拟手续费、现金、持仓和交易记录。
5. `simulation` 聚合多只股票的当日收益，并支持组合级动量轮动。
6. `web` 用原生 SVG 画出类似 graphing calculator 的坐标网格与曲线。

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
| `QUANT_STRATEGY` | `sma_cross` | Pages 快照使用的策略 key |
| `QUANT_UNIVERSE` | `custom` | 股票池 key |
| `QUANT_TOP_N` | `10` | 组合级策略持仓数量 |
| `QUANT_RANGE` | `6mo` | 历史数据范围 |
| `QUANT_INTERVAL` | `1d` | K 线周期 |

也可以本地生成同样的静态站点：

```bash
QUANT_TRADER_OFFLINE=1 python3 -m quant_trader.static_site --output public --symbols AAPL,MSFT,NVDA --strategy regime_adaptive --range 1y --interval 1d
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
curl "http://127.0.0.1:8000/api/simulate?symbols=AAPL,MSFT,NVDA&cash=100000&strategy=dual_momentum&range=1y&interval=1d"
```

常用参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `symbols` | `AAPL,MSFT` | 逗号分隔股票代码 |
| `universe` | `custom` | 股票池 key；非 `custom` 时优先使用预设股票池 |
| `strategy` | `sma_cross` | 策略 key，见上方策略表 |
| `cash` | `100000` | 初始纸面资金 |
| `fast` | `12` | 快速 SMA 窗口 |
| `slow` | `26` | 慢速 SMA 窗口，必须大于 fast |
| `top_n` | `10` | 多因子/组合级策略的目标持仓数量 |
| `commission` | `0.001` | 单边手续费率 |
| `range` | `6mo` | Yahoo chart range；历史策略建议 `6mo`、`1y` 或更长 |
| `interval` | `1d` | Yahoo chart interval；可切换 `1d` 历史日线或 `1m`/`5m` 日内 |

网页状态卡会显示：

- 当前交易状态。
- 所选股票交易所时区的当前实际时间。
- 最新行情 bar 的交易所本地时间。
- 当前策略和数据周期。

## 项目结构

```text
quant_trader/
  storage.py       # SQLite 行情缓存
  factors.py       # 多因子打分
  metrics.py       # 回测报告指标
  indicators.py    # SMA、RSI、布林带、动量等复用指标
  market_data.py   # 行情拉取与样例行情
  market_calendar.py # 美股交易日历、时区和常规时段
  strategy.py      # 策略注册表与信号生成
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
- 增加 regime detector、仓位管理、止损/止盈和波动率目标。
- 将模拟状态持久化到 SQLite，方便复盘每日交易。
- 引入 WebSocket 或 Server-Sent Events，减少轮询刷新。