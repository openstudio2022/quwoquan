# L3 特性：daily-merge-release-strategy

## 功能说明

建立「日常代码仅合入 dev1.0 + 每日定时自动合并至 main + 合并后触发 deploy integration 与 prod 首阶段」的 release 策略，实现端到端自动化。

## 范围

- **分支策略**：日常 PR 仅合入 dev1.0；main 仅由定时 merge 更新
- **定时 merge**：每日早晨（如 6:00 Asia/Shanghai）自动 merge dev1.0 → main
- **部署触发**：main 更新后自动触发 pre-release-gate（deploy integration）及 deploy-prod-auto（Stage 1 初始灰度）

## 适用范围与约束

- **适用**：日节奏发布、integration/prod 自动化部署
- **约束**：需 GitHub Actions 权限（PAT 或 GITHUB_TOKEN 用于 merge）；deploy-prod-auto 依赖 pre-release-gate 通过
- **不适用**：紧急 hotfix 直推 main（可保留 workflow_dispatch 或临时放开策略）

## 与父/子节点关系

**父节点**：deliver-deploy-prod-pipeline（L2）

| 关联节点 | 说明 |
|----------|------|
| integration-deploy-and-l3-l4-gate | pre-release-gate 需支持 push to main 触发 |
| gray-release-to-prod | deploy-prod-auto Stage 1 全自动 |

## 多环境与波次（跨节点口径）

**五类逻辑环境**（alpha / beta / gamma / prod-gray / prod）与 **B→C→(D→E)** 大波段、prod 内 **wave**，以 **[environment_matrix.md](../../../../../deploy/shared/environment_matrix.md)** 为总览，与 [ci_cd_end_to_end_design.md](../../../../../deploy/shared/ci_cd_end_to_end_design.md) 一致。

## 验收标准概要

- A1：分支策略文档明确「日常 PR → dev1.0」「main 仅由定时 merge 更新」
- A2：merge-dev1.0-to-main workflow 定时执行（cron）并可 workflow_dispatch
- A3：merge 成功后触发 pre-release-gate（或等效 deploy integration）
- A4：pre-release-gate 通过后 deploy-prod-auto Stage 1 自动执行
- A5：deliver_to_production_runbook、ci_cd_end_to_end_design 与策略一致
- A6：环境矩阵与上述 release 波次、Secrets（含 `GAMMA_PRODUCT_OPS_BASE_URL`）在文档层面对齐
