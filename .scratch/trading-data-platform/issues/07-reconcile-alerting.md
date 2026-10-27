# 07: 对账熔断与告警

**What to build:** 对账任务：每 5 分钟拉 Binance 账单 API 与本地 fills 逐笔比对，差异即告警并熔断（停止交易，只能人工复核恢复）。告警：企业微信群机器人主通道 + 邮件兜底（双通道互不依赖）；必推事件：熔断、对账差异、数据水位过期；心跳每日一报。凭据存服务器本地 `.env`。降级遵循仓库既有模式：告警通道不可达不影响交易安全状态本身。

**Blocked by:** 05、06

**Status:** ready-for-human (code complete + unit tests green; WeCom/SMTP/Binance API 联调待服务器)

- [x] 对账逐笔比对实现（按 exchange trade id），差异→告警→熔断链路测试通过
- [x] 熔断后所有下单路径拒绝执行，恢复仅限人工显式 reset
- [x] 双通道告警（企微 webhook + SMTP 邮件）实现，通道故障互不影响且不影响熔断状态（测试证明）
- [ ] 心跳日报与水位过期告警定时触发（随 08 部署体系联调）
- [ ] 企微/SMTP/Binance API 真实凭据联调（服务器）
