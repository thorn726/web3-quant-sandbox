# 01: 红线修订与模块骨架

**What to build:** 将"永不接实盘"红线修订为"缺省 research-only"：实盘执行能力由显式配置开启（缺省关闭），verify.py 的边界校验改为校验"缺省配置下无实盘能力"并保持全绿。建立模块骨架：`src/market_data/`（空管道包）与 `src/trading/`（空执行包），与现有 src/research、src/backtest、src/dashboard 物理隔离；README/AGENTS.md 中红线表述同步修订。CONTEXT.md 已建，随实现补充术语。

**Blocked by:** None (can start immediately)

**Status:** ready-for-human (code complete; full `make verify` pending npm access — pytest equivalent run locally: 214 passed)

- [x] verify.py 缺省配置下校验通过，实盘功能默认不可达
- [x] 显式开启配置后边界校验放行（仅配置层，无执行代码）
- [x] src/market_data/ 与 src/trading/ 骨架建立，互不依赖
- [x] README/AGENTS.md 红线表述修订一致
- [ ] make verify 全绿（本机沙盒禁 npm，待服务器验证）
