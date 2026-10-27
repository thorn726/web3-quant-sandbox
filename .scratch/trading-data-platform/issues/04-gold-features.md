# 04: Gold 层因子/特征表

**What to build:** gold 层：从 silver 派生因子/特征表，供现有 src/research、src/backtest 及未来执行层只读消费。与现有因子研究模块（src/factor_mining）的输入打通，替代教学 fixture 成为研究数据的真实来源（fixture 保留为教学兜底）。特征表 schema 版本化，重算幂等。

**Blocked by:** 03

**Status:** ready-for-human (code complete; all checks green)

- [x] 至少一组特征表从 silver 派生并可被 backtest 消费（log_return / sma_5_20_ratio / volatility_20 / volume_zscore_20）
- [x] schema 有版本标识，重算不产生重复/冲突（features-v{N}.parquet + meta 侧车，重建字节级一致）
- [x] 教学沙盒原有数据路径不回归（全量 234 passed）
