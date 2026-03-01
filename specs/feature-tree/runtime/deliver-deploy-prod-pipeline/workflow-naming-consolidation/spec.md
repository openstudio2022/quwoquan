# L3 特性：workflow-naming-consolidation

## 功能说明

统一 6 个 GitHub Actions Workflow 的命名规范：序号 + 首字母大写 + 环境标注，并校验 02 Service Pipeline 与 03 Delivery Gate 无重复执行。

## 范围

- **命名规范**：01. App Pipeline → 06. Deploy To Prod (Auto)，首字母大写
- **环境标注**：Main Branch / Integration / Production — Gray / Production — Full
- **02/03 去重检查**：确认 Service Pipeline 与 Delivery Gate 职责互补、无冗余执行

## 适用范围与约束

- **适用**：deliver-deploy-prod-pipeline 下所有 workflow；与 workflow_consolidation_plan 对齐
- **约束**：deploy-prod-auto 的 workflow_run 需引用「04. Pre-Release Gate」名称
- **不适用**：非 workflow 命名、非 02/03 的 pipeline

## 与父/子节点关系

**父节点**：deliver-deploy-prod-pipeline（L2）

| 关联节点 | 说明 |
|----------|------|
| integration-deploy-and-l3-l4-gate | 含 04. Pre-Release Gate |
| gray-release-to-prod | 含 05/06 Deploy To Prod |

## 验收标准概要

- A1：6 个 workflow name 为 01～06 序号 + 首字母大写
- A2：workflow_consolidation_plan 含命名规范与 02/03 重复检查
- A3：deploy-prod-auto workflow_run 正确引用 04. Pre-Release Gate
- A4：ci_cd_end_to_end_design、deliver_to_production_runbook 与规范一致
