# 03: 生产运维文档与最终验收

**What to build:** README 新增生产部署章节：前置条件、从零部署命令序列、防火墙白名单配置（仅放行用户 IP 到服务端口，无域名 HTTP 直连）、LLM API key 配置到服务器本地 .env（不进 git）、离线重部署说明、日常运维（状态/日志/手动刷新）。然后按规格的四条验收标准在真实服务器上完整验收：① 重启自动恢复；② 一条命令序列从零部署；③ 快照定时刷新且断网降级；④ 服务器上 make verify 全绿 + 核心页面实际操作通过。

**Blocked by:** 01、02

**Status:** ready-for-human (code complete; server acceptance pending)

- [ ] README 生产部署章节完整，照着能在新服务器走通
- [ ] 防火墙配置方法写入文档（含云安全组与系统防火墙两种写法）
- [ ] LLM key 配置说明写入文档，.env 不进 git
- [ ] 四条验收标准逐条在服务器上实测通过并记录
