# 开发任务：daily-merge-release-strategy

## 当前交付任务

- T1 更新 `deploy/shared/branch_strategy.md`：取消定时 merge，补充显式 PR + required checks 与两种开发模式
- T2 删除 `.github/workflows/merge-dev1.0-to-main.yml`
- T3 调整 `delivery-gate.yml`、`pre-release-gate.yml`、`app-env-device-matrix-self-hosted.yml` 只在 `pull_request(main)` / 手动路径承担主干阻断
- T4 清理 `05` wrapper，保留单一 self-hosted 设备矩阵入口
- T5 调整 `service_pipeline.yml`、`deploy-prod-auto.yml` 为 post-main 动作
- T6 更新 runbook / CI 设计 / workflow 说明，移除定时 merge 口径

### T — 实施


| 任务  | 说明                                                            | 状态  |
| --- | ------------------------------------------------------------- | --- |
| T1  | branch_strategy.md：显式 PR + required checks，覆盖 dev1.0 / trunk 两种模式 | [x] |
| T2  | 删除 merge-dev1.0-to-main workflow 与配套脚本                        | [x] |
| T3  | 03/04/05 改为 PR 阻断                                              | [x] |
| T4  | 05 设备矩阵收敛为唯一 self-hosted 入口                                   | [x] |
| T5  | 02/07 改为 main 后动作；08 保留手动                                     | [x] |
| T6  | 文档与说明同步收口                                                     | [x] |


## 搁置任务

无。

## 未来演进任务

- 为 `03/04/05` 增加更细粒度的 changed-files 优化，减少 PR 等待
- 将 `main` required checks 与 branch protection 配置沉淀到 runbook / repo settings checklist