# 开发任务：risky-config-gray-release

## 统一门禁矩阵（灰度侧补充）

| 阶段命令 | 灰度补充必过项（最小集） | 不通过处理 |
|---|---|---|
| `/prd` | 高风险配置清单与灰度步骤（5/25/50/100）已写入 tasks/acceptance | 阻断 FF |
| `/design` | 发布阶段门禁（错误率/延迟/依赖失败率）可运行 | 阻断 apply |
| `/commit` / submit-with-gate | 高风险字段变更必须附回滚版本与门禁结果 | 禁止提交入库 |

## 当前交付任务（按阶段）

### Wave 1 — 灰度策略与发布版本

- [x] G1 定义高风险配置白名单与审批规则
- [x] G2 实现配置发布版本号与阶段计划（5/25/50/100）
- [x] G3 接入灰度控制器（Rollout/Deployment progressive strategy）

### Wave 2 — 门禁联动与自动止损

- [x] G4 接入阶段门禁（错误率、延迟、依赖失败率）
- [x] G5 发布失败自动停止并调用回滚流程
- [x] G6 增加发布门禁：
  - 校验每阶段实例组必须同时声明 `IMAGE_VERSION` 与 `CONFIG_VERSION`
  - 校验 `CONFIG_VERSION` 可在版本目录定位到文件
  - 校验生产必须使用外部挂载配置根路径

### Wave 3 — deliver 联调

- [x] G7 完成与 `one-click-config-rollback` 联调演练
- [x] G8 完成与 `slo-error-budget-governance` 门禁联调演练
- [x] G9 输出灰度发布与自动回滚演练报告（deliver 必备）
  - `deploy/service/config-release/reports/2026-02-27-config-release-drill.md`
- [ ] Migrated current node: `one-click-config-rollback` (from `platform-ops-governance/config-and-reliability-governance/config-source-governance/risky-config-gray-release/one-click-config-rollback`)

## 搁置任务（带规划）

- [ ] G10 多集群联动灰度（跨地域）
  - 搁置原因：当前先完成单集群闭环

## 未来演进任务

- [ ] G11 支持按租户/流量标签灰度
- [ ] G12 发布策略自动推荐（基于记录稳定性）

## Folded current node `one-click-config-rollback`

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
