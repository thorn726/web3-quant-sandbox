# 08: 部署集成与最终验收

**What to build:** 部署体系扩展：现有 make 部署目标 + systemd 体系增加交易 worker 与数据管道 timer 两类服务，与沙盒 Web 服务相互独立（交易服务可单独停/启，不影响教学站）。README 新增数据底座与交易系统章节：部署序列、`.env` 凭据项、备份纪律、告警配置、paper→实盘切换清单。服务器上完整验收：从零部署、回填、定时刷新、断源降级、paper trading 运行、对账熔断演练。

**Blocked by:** 02、03、04、05、06、07

**Status:** ready-for-human (code + docs complete; server acceptance pending)

- [x] 新增 make 目标：`deploy-data-timer` / `deploy-trading-timer` / `marketdata-*` / `trading-status` / `trading-logs`
- [ ] 服务隔离：停交易服务不影响沙盒 Web，实测（服务器）
- [x] README「数据底座与交易系统」章节完整可照做（部署序列、.env 配置表、安全模型、paper→实盘清单）
- [ ] 服务器验收逐条实测并记录（含一次人为对账差异触发的熔断演练）
