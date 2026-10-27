# 02: Bronze 层管道（回填 + 增量 + 调度）

**What to build:** `src/market_data/` bronze 层：用 Binance Vision 官方 dump 一次性回填 Binance 现货日线/分钟线 K 线历史（Parquet 按月分区）；ccxt REST 做增量更新；systemd timer 定时调度（沿用现有 fixture 架构模式：日志、幂等、可重跑）。bronze 只增不改（append-only），每个数据集记录新鲜度水位（last good timestamp）。断源时管道失败有日志、水位不前进，不影响任何下游服务。

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Binance Vision 回填跑通，数年分钟线落为 Parquet 月分区
- [ ] 增量更新任务幂等，重复执行不产生重复数据
- [ ] bronze 层内容永不改写（可用测试证明：二次写入同区间不覆盖）
- [ ] 水位表存在且随成功刷新前进
- [ ] 断源模拟：任务失败有日志、旧数据完好、无副作用
