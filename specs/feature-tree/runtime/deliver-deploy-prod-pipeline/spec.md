# L2 特性：deliver-deploy-prod-pipeline

## 功能说明

沿用当前 `alpha-local / beta-local / gamma-hosted / prod-hosted` 混合拓扑，把环境打包、启动、健康检查、端云集成验证、灰度发布与证据归档统一收敛到 `stackctl` 与 GitHub Actions。目标是让 `main` 入库后自动完成 `alpha -> beta -> gamma -> prod` promotion 主链，并在 `prod initial -> prod full` 之间自动执行健康探针、只读集成探针、SLO gate 与 auto rollback。

主链分层如下：

- `03. Delivery Gate` 继续负责 PR 前 L1/L2 静态与模块收敛。
- `04. Pre-Release Gate` 继续负责 PR 前 gamma hosted 轻量预检，不承担 `main` 后真 promotion。
- `05. App Env Device Matrix` 继续负责 self-hosted 设备矩阵，并新增可供 `main` promotion 复用的 `mainline_auto_prod` profile。
- `07. Deploy To Prod (Auto)` 演进为 `main` 入库后的单一自动 promotion workflow。

## 范围

- **PR 前置收敛**：`03/04/05` 保持 required checks 名称稳定，继续负责进入 `main` 前的质量收敛。
- **main 自动 promotion**：`repo verify/package -> alpha-local -> beta-local -> gamma-hosted -> prod initial -> prod checks -> prod full`。
- **统一验证 profile**：`deploy/shared/gamma_validation_suites.json` 统一定义 `pr_light / manual_full / nightly_full / release_candidate / mainline_auto_prod`。
- **统一证据归档**：每个 promotion 阶段必须落 `artifacts/stackctl/<env>/<run-id>/report.json` 与 `summary.md`，workflow 同步上传 artifact。
- **15 分钟硬预算**：阻断主链的 `critical_path_seconds <= 900`，重型 Patrol/full semantic/全设备全旅程留在 `nightly_full` 与 `release_candidate`。
- **local-gamma left shift**：仍作为提交前左移预测试拓扑，但不替代 `main` 后自动 promotion。

## 适用范围与约束

- **适用**：PR 前 required checks、`main` 后自动 promotion、gamma hosted 复验、prod 自动灰度、prod 自动回滚。
- **不适用**：新增 `beta-hosted`、`prod-gray` 等额外环境名或第二套拓扑命名。
- **约束**：
  - `03/04/05` 名称与 required-check 语义必须保持稳定。
  - `stackctl` 是环境自动化唯一入口；workflow 只编排，不复制第二套环境逻辑。
  - `prod` 灰度是 `prod` 语义下的 rollout stage，不得再引入独立环境枚举。
  - `mainline_auto_prod` 只保留高信号阻断链：beta 设备矩阵、gamma readiness/T3/high-signal probes、prod 初始灰度后的只读集成探针。
  - 自动升 `prod full` 的前提是 auto rollback、SLO gate、stage evidence 与 release-state 一致性先落地。

## 与父/子节点关系

**父节点**：runtime（L1 能力域）

| 子节点 | 职责 | 优先级 |
|--------|------|--------|
| **multi-environment-wave-deployment** | 冻结 `alpha-local / beta-local / gamma-hosted / prod-hosted` 拓扑与主链波次关系 | **优先** |
| **gray-release-to-prod** | `prod initial / prod full`、SLO gate、rollback 与 release-state 一致性 | **优先** |
| **local-gamma-mirror** | 提交前左移预测试，复用 gamma 语义但不进入 `main` 阻断主链 | **并行配套** |
| **multi-environment-instance-isolation** | 本地 alpha/beta 多设备并行与 beta/gamma 单套服务生命周期 | **并行配套** |

## 验收标准概要

- A1：`main` push 触发单一 workflow，按固定顺序执行 `repo verify/package -> alpha-local -> beta-local -> gamma-hosted -> prod initial -> prod checks -> prod full`。
- A2：`alpha-local` 阶段必须完成环境包、启动与 `stackctl health --scope full`，并落证据产物。
- A3：`beta-local` 阶段必须完成 `stackctl up/health/inspect` 与 self-hosted beta 设备矩阵，通过后才能进入 gamma。
- A4：`gamma-hosted` 阶段必须通过 hosted deploy、readiness、T3 API contract、assistant protocol smoke、chat avatar probe，且这些阻断项由 `mainline_auto_prod` 单源描述。
- A5：`prod initial -> prod checks -> prod full` 默认全自动，不再依赖人工 approval。
- A6：`prod checks` 或 `prod full` 失败时，workflow 必须自动回滚到上一稳定 `image/config` 并恢复 ready 状态。
- A7：每个阶段都能输出 `report.json`、`summary.md`、stdout/diagnostics，支持人工排障与 workflow 复用。
- A8：主链耗时摘要必须落关键路径统计，并以 `critical_path_seconds <= 900` 作为硬门禁。
