# Quant Paper Trader

一个轻量级量化模拟交易教学项目：从公开日内行情拉取数据，运行移动均线交叉策略，使用纸面账户模拟买卖，并用网页展示当日收益、所选股票涨跌曲线、持仓和交易记录。

> 免责声明：本项目仅用于编程、量化入门和模拟交易教学，不构成投资建议，也不会向真实券商下单。

## 为什么选 SMA 交叉策略

高 star、社区认可度较高的量化/回测项目经常用双均线交叉作为第一个教学策略：

- [`kernc/backtesting.py`](https://github.com/kernc/backtesting.py)：高 star Python 回测库，官方示例包含 `SmaCross`。
- [`polakowo/vectorbt`](https://github.com/polakowo/vectorbt)：高 star 向量化量化研究框架，示例中也常用 fast/slow MA 生成交易信号。

本仓库没有直接复制这些项目的代码，而是把核心思想重构为更小、更易读的教学实现：

1. `market_data` 拉取 Yahoo Finance 日内 chart 数据，网络不可用时用样例行情兜底。
2. `strategy` 计算 fast/slow SMA，并在交叉时生成 `buy` / `sell` 信号。
3. `broker` 使用纸面账户模拟手续费、现金、持仓和交易记录。
4. `simulation` 聚合多只股票的当日收益。
5. `web` 用原生 SVG 画出类似 graphing calculator 的坐标网格与曲线。

## 快速开始

本项目只依赖 Python 标准库，Python 3.10+ 即可运行。

```bash
python -m quant_trader.server --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

如果希望强制离线演示：

```bash
QUANT_TRADER_OFFLINE=1 python -m quant_trader.server
```

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
  strategy.py      # SMA 交叉信号
  broker.py        # 纸面经纪账户
  simulation.py    # 多股票组合模拟
  server.py        # HTTP API + 静态页面服务
web/
  index.html
  styles.css
  app.js           # 原生 SVG 可视化
docs/
  tutorial.md      # 教学说明
tests/
  test_strategy.py
```

## 测试

```bash
python -m unittest discover -s tests
```

## 后续扩展方向

- 接入正式券商 sandbox，例如 Alpaca Paper Trading 或 Interactive Brokers Paper Account。
- 增加更多策略指标，例如 RSI、布林带、动量轮动。
- 将模拟状态持久化到 SQLite，方便复盘每日交易。
- 引入 WebSocket 或 Server-Sent Events，减少轮询刷新。