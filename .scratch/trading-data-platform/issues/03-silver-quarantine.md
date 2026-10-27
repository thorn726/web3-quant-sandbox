# 03: Silver 层清洗与隔离区

**What to build:** silver 层：从 bronze 读取并清洗为标准 K 线（统一时区 UTC、统一精度、去重、补洞标记）。完整性校验三规则：high≥low（含 open/close 在区间内）、volume≥0、时间连续性；校验失败的数据进 quarantine（隔离区，保留不删、不进 silver）。水位对下游可见（gold/研究/未来执行层均可查询每个数据集的新鲜度）。pytest 覆盖：坏数据进隔离区、好数据正常通过、下游读到水位。

**Blocked by:** 02

**Status:** ready-for-human (code complete; all checks green)

- [x] silver 标准化跑通，时区/精度/去重/补洞标记齐备（gap_after 标记，UTC 毫秒，open_time 去重）
- [x] 三条校验规则实现，坏样本进 quarantine 且可查（ohlc_range / negative_volume / duplicate_open_time / bad_open_time 分类落盘）
- [x] 下游可查询各数据集水位（silver.watermark()）
- [x] 降级 pytest 覆盖并通过（5 条）
