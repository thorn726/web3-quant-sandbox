# 规格：真实交易数据底座（本仓库重构）

Status: ready-for-human (design agreed 2026-10-27; risk values pending)

## Problem Statement

项目目前的数据层是教学沙盒口径：fixture + 快照兜底，无原始数据留存、无数据分层、无执行侧数据。要演化为可依赖的真实交易系统，需要一个可靠的数据底座支撑研究与实盘。

## 定案决策（2026-10-27 拷问会共识）

### 范围

1. **完整口径、分阶段**：先行情数据管道（bronze→silver→gold），执行侧（账本/风控/执行器）随后，最后接入实盘。
2. **本仓库重构，不新建仓库**：沙盒教学功能保留不动。
3. **红线修订**：由"永不接实盘"改为"**默认 research-only，实盘功能由显式配置开启（缺省关闭，verify 校验缺省为关）**"。
4. **交易对象**：Binance CEX 现货。数据范围：日线/分钟线 K 线 + 少量链上聚合；订单簿 L2 与逐笔 tick 不做。
5. **实时性**：分钟级轮询批处理，不做流式架构。
6. **规模**：单台 4C8G VPS + 对象存储放历史冷数据，预算 $20–50/月。

### 架构

7. **存储**：Parquet 文件 + DuckDB 查询，按月分区；不引入数据库。
8. **数据分层**：bronze（交易所原始响应，append-only 永不修改）→ silver（清洗标准 K 线：去重、补洞标记、统一时区精度）→ gold（因子/特征表）；执行账本与行情平级、不混流。
9. **历史回填**：Binance Vision 官方全量 dump 一次性回填；ccxt REST 做增量更新。
10. **调度**：systemd timer + Python 脚本（沿用现有 fixture 架构模式），每步落运行日志与数据新鲜度水位表，幂等可重跑。
11. **模块隔离**：`src/market_data/`（三层管道）与 `src/trading/`（账本、风控、执行器、对账）物理隔离；现有 src/research、src/backtest、src/dashboard 不动；两者唯一共享点是 market_data 只读访问。沙盒 Web 服务与交易 worker 为两个独立 systemd 服务。
12. **执行账本**：SQLite（WAL 模式），orders/fills/positions，append-only，与交易所账单对账；备份靠单文件 rsync 纪律。

### 质量与安全

13. **数据质量三防线**：① K 线完整性校验（high≥low、volume≥0、时间连续性）；② 校验失败进 quarantine 不进 silver；③ 每个数据集有新鲜度水位（last good timestamp），下游可见。
14. **对账熔断**：每 5 分钟拉交易所账单与本地 fills 逐笔比对，差异即告警并**熔断停止交易**（不容妥协项）。
15. **风控硬边界**（数值预留，见 Open Items）：单笔最大金额、单币种最大仓位、日最大亏损额（触发即当日停止）、API key 只开交易权限不开提现。写死在执行路径，策略层无权绕过。
16. **上线路径**：paper trading ≥4 周、对账零差异、无未处理告警后方可切实盘；切盘只换配置不改代码。
17. **告警**：企业微信群机器人为主通道 + 邮件兜底（双通道互不依赖）。必推事件：熔断、对账差异、数据水位过期；心跳每日一报。

## Open Items

- 风控三个数值（单笔上限、仓位上限、日亏损上限）——用户预留，动工执行模块前必须补齐。
- API key / 企微 webhook / SMTP 凭据均存服务器本地 `.env`，不进 git（沿用现有机制）。

## Out of Scope

- 订单簿 L2 / 逐笔 tick 数据；流式架构（Kafka/Flink）；多交易所；第二家交易所；多用户；Docker。

## 验收口径（后续拆 issues）

- bronze 层可回填 Binance 全量历史分钟线并增量更新，bronze 永不改写可验证。
- 断源时：管道报错有日志、水位不前进、下游读旧数据不崩（快照降级思想推广）。
- quarantine 与水位对下游可见。
- 红线修订后 `make verify` 全绿（缺省配置 research-only）。
- 执行侧各阶段验收在动工时另行拆分。
