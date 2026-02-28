# 开发任务：one-click-config-rollback

## 当前交付任务（与灰度联动）

### Wave 1 — 回滚核心能力

- [x] R1 定义稳定版本记录结构（current/stable/candidate）
- [x] R2 实现回滚 API/CLI（指定或自动回退）
- [x] R3 实现回滚后的工作负载滚动重载
- [x] R4 实现回滚幂等与并发保护
- [x] R5 增加回滚审计事件与告警

### Wave 2 — 演练与 deliver

- [x] R6 完成自动化演练：发布失败 -> 回滚成功
- [x] R7 完成“老镜像+老配置 / 新镜像+新配置”回滚场景演练
- [x] R8 输出回滚 Runbook 与演练报告（deliver 必备）
  - `deploy/service/config-release/runbook.md`
  - `deploy/service/config-release/reports/2026-02-27-config-release-drill.md`

## 搁置任务（带规划）

- [ ] R9 跨服务事务性回滚（多服务联动）
  - 搁置原因：当前先完成单服务回滚闭环

## 未来演进任务

- [ ] R10 回滚策略智能选择（按失败类型选择目标版本）
