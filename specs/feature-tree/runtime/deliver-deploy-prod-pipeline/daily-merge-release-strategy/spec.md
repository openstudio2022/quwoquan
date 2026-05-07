# L3 特性：daily-merge-release-strategy

## 功能说明

建立「显式 PR + required checks 进入 main」的 release 策略，替代旧的“每日定时自动合并 `dev1.0 -> main`”模型。

## 范围

- **分支策略**：支持 `dev1.0` 分支开发与 trunk development，但进入 `main` 统一走显式 PR
- **PR 合入规则**：`main` 的 required checks 统一由 `03/04/05` 承担，其中 `04` 是 ECS gamma 主门禁、`05` 是本地 self-hosted alpha/beta Android+iOS 设备矩阵
- **部署触发**：进入 `main` 后自动触发 `02` 与 `07`，手动发布保留 `06/08`

## 适用范围与约束

- **适用**：日节奏发布、ECS gamma / prod 自动化部署
- **约束**：需 GitHub Actions 权限（PAT 或 GITHUB_TOKEN 用于 merge）；deploy-prod-auto 依赖 `03/04/05` 全绿
- **不适用**：紧急 hotfix 直推 main（可保留 workflow_dispatch 或临时放开策略）

## 与父/子节点关系

**父节点**：deliver-deploy-prod-pipeline（L2）

| 关联节点 | 说明 |
|----------|------|
| integration-deploy-and-l3-l4-gate | 已收口为 ECS gamma hosted pre + 本地 self-hosted gamma 旅程 |
| gray-release-to-prod | deploy-prod-auto Stage 1 全自动 |

## 多环境与波次（跨节点口径）

**五类逻辑环境**（alpha / beta / gamma / prod-gray / prod）与 **B→C→(D→E)** 大波段、prod 内 **wave**，以 **[environment_matrix.md](../../../../../deploy/shared/environment_matrix.md)** 为总览，与 [ci_cd_end_to_end_design.md](../../../../../deploy/shared/ci_cd_end_to_end_design.md) 一致。

## 验收标准概要

- A1：分支策略文档明确「显式 PR + required checks 进入 main」，且不再存在定时 merge 口径
- A2：`03` / `04` / `05` 仅在 `pull_request(main)` / 手动路径运行，不在分支 push 上重复执行
- A3：PR required checks 全绿后进入 `main`
- A4：进入 `main` 后触发 `02` 与 `07`
- A5：deliver_to_production_runbook、ci_cd_end_to_end_design 与策略一致
- A6：环境矩阵与上述 release 波次、ECS gamma / self-hosted Android+iOS 口径在文档层面对齐
