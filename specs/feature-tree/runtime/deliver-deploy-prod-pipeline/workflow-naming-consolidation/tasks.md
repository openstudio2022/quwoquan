# 开发任务：workflow-naming-consolidation

## 当前交付任务

- [x] T1 统一 01～08 的名称与边界
- [x] T2 删除重复入口（05 wrapper、07 定时合流）
- [x] T3 调整重复编号（08c 回滚）
- [x] T4 更新命名规范文档与 CI 设计文档

### T — 实施

| 任务 | 说明 | 状态 |
|------|------|------|
| T1 | 主工作流名称统一为 01～08 | [x] |
| T2 | 删除 `merge-dev1.0-to-main.yml` 与 `app-env-device-matrix.yml` | [x] |
| T3 | `ecs-onebox-rollback.yml` 更名为 `08c. ECS Onebox Rollback` | [x] |
| T4 | `workflow_consolidation_plan.md` / `ci_cd_end_to_end_design.md` / `branch_strategy.md` 同步 | [x] |

## 搁置任务

无。

## 未来演进任务

- 若新增 workflow，继续沿用 09、10… 序号
