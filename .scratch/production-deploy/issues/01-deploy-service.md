# 01: 一键部署与服务自启

**What to build:** 在一台全新服务器上，按 README 的命令序列执行新增的 make 部署目标，从零（无 venv、无依赖、未构建）到服务运行：venv 创建、依赖安装、前端构建、systemd unit 安装并启动。服务崩溃时自动重启，服务器重启后自动恢复，可用 systemctl 查看状态与日志。沿用现有 setup/verify 目标，不重复造轮子。

**Blocked by:** None (can start immediately)

**Status:** ready-for-human (code complete; server acceptance pending)

- [ ] 全新目录拉取仓库后，按 make 目标序列一条条执行即可服务运行，HTTP 端口可访问
- [ ] systemd unit 含 Restart=on-failure 与开机自启（multi-user.target）
- [ ] 手动 kill 服务进程后 systemd 自动拉起
- [ ] 提供状态查看与日志查看的 make 目标
- [ ] 部署序列中任一步失败时报错清晰、可重跑（幂等）
