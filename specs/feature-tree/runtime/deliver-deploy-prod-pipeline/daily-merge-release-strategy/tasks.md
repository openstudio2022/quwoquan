# 开发任务：daily-merge-release-strategy

## 当前交付任务

- [x] T1 创建 deploy/shared/branch_strategy.md（分支策略：日常 PR→dev1.0，main 仅定时 merge）
- [x] T2 创建 .github/workflows/merge-dev1.0-to-main.yml（scheduled + workflow_dispatch）
- [x] T3 修改 pre-release-gate.yml 增加 on.push.branches: [main]，并处理 merge 场景版本号
- [x] T4 更新 deliver_to_production_runbook、ci_cd_end_to_end_design 与 branch_strategy 一致
- [x] T5 更新 workflow_consolidation_plan 增加 07 merge-dev1.0-to-main 说明

### T — 实施

| 任务 | 说明 | 状态 |
|------|------|------|
| T1 | branch_strategy.md：dev1.0 日常合入、main 定时 merge、GitHub 分支保护建议 | [x] |
| T2 | merge-dev1.0-to-main.yml：cron 6:00 Asia/Shanghai，git merge dev1.0→main，push | [x] |
| T3 | pre-release-gate 增加 push main 触发 | [x] |
| T4 | runbook、ci_cd_end_to_end_design 引用 branch_strategy | [x] |
| T5 | workflow_consolidation_plan 增加 07 序号 | [x] |

## 搁置任务

无。

## 未来演进任务

- 增加 merge 前「dev1.0 领先 main」检查，避免空 merge
- merge 冲突时增加通知（Slack/钉钉/issue）
- 支持多时区 cron 配置
