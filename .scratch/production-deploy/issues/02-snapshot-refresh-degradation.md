# 02: 快照定时刷新与断网降级

**What to build:** systemd timer 定时执行现有快照 fixtures 构建脚本，保持仪表盘数据新鲜；数据源不可达（断网/限频）时刷新失败不产生副作用：旧快照文件保留，/api/dashboard/* 继续以旧快照正常响应，服务不报错不崩溃。为本降级行为补一条 pytest（测试 dashboard fixture 模块的外部行为，风格随现有 tests/）。刷新失败有日志可查。

**Blocked by:** 01（timer 安装复用部署目标体系）

**Status:** ready-for-human (code complete; server acceptance pending)

- [ ] systemd timer 启用，按配置周期触发刷新，触发记录在日志中可见
- [ ] 模拟断网/数据源不可达时：刷新任务失败但旧快照未被破坏，API 正常返回旧数据
- [ ] 降级行为有 pytest 覆盖且通过
- [ ] 刷新成功路径实测：快照文件时间戳更新，API 返回新数据
