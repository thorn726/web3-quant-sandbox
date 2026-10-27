# 05: 执行账本（SQLite）

**What to build:** `src/trading/` 执行账本：SQLite（WAL 模式）存 orders/fills/positions，append-only（改单写成新记录 + 状态指针，不 UPDATE 历史行）。schema 版本化；单文件 rsync 备份脚本；账本写入与行情读取（market_data 只读共享点）隔离。pytest 覆盖：append-only 不可变、状态机合法流转、并发写（WAL）安全。

**Blocked by:** 01

**Status:** ready-for-human (code complete; all checks green)

- [x] orders/fills/positions 表建立，append-only 有测试证明
- [x] WAL 模式启用，备份脚本跑通
- [x] 状态流转（pending→filled/cancelled 等）只允许合法路径
- [x] 与 market_data 的共享仅限只读，有结构保证
