# 06: 风控边界与 paper trading 执行器

**What to build:** paper trading 执行器：经账本模拟下单（paper 模式无真实 API 调用）。风控四条硬边界写死在执行路径（策略层无权绕过）：单笔最大金额、单币种最大仓位、日最大亏损额（触发即当日停止）、API key 权限最小化（只交易无提现——配置校验项）。风控数值经环境变量配置（TRADING_MAX_ORDER_QUOTE / TRADING_MAX_POSITION_QUOTE / TRADING_DAILY_LOSS_QUOTE），缺任一项拒绝交易。切实盘 = 换配置不改代码，缺省 research-only 红线在此收口。

**Blocked by:** 04、05（已全部完成）

**Status:** ready-for-human (code complete; paper trading ≥4 周运行验收待服务器)

- [x] paper 模式全流程跑通：信号→风控校验→账本记录
- [x] 风控边界经配置注入并在执行路径强制，绕过路径被测试否定
- [x] 日亏损触发当日停止（基于账本事实重算，次日 UTC 日自动恢复）
- [ ] API key 权限最小化校验（随 07 联调）
- [ ] paper trading 稳定运行 ≥4 周、对账零差异、无未处理告警后方可切实盘（验收在服务器）
