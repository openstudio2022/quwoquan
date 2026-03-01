# 开发任务：workflow-naming-consolidation

## 当前交付任务

- [x] T1 更新 6 个 workflow 的 name 为序号 + 首字母大写
- [x] T2 更新 deploy-prod-auto workflow_run 引用「04. Pre-Release Gate」
- [x] T3 更新 workflow_consolidation_plan 含命名规范与 02/03 重复检查
- [x] T4 确保 ci_cd_end_to_end_design、deliver_to_production_runbook 与规范一致

### T — 实施

| 任务 | 说明 | 状态 |
|------|------|------|
| T1 | 6 个 workflow name：01. App Pipeline ～ 06. Deploy To Prod (Auto) | [x] 已完成 |
| T2 | deploy-prod-auto workflow_run workflows: ['04. Pre-Release Gate'] | [x] 已完成 |
| T3 | workflow_consolidation_plan §2 命名规范 + §4.6 02/03 重复检查 | [x] 已完成 |
| T4 | ci_cd_end_to_end_design、runbook 引用规范命名 | [x] 已完成 |

## 搁置任务

无。

## 未来演进任务

- 新增 workflow 时延续 07、08 序号
