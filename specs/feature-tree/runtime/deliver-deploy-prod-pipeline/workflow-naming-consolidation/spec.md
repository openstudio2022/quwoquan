# L3 特性：workflow-naming-consolidation

## 功能说明

统一主干治理后的 GitHub Actions Workflow 命名规范：01～08 顺序唯一、名称可在 Actions UI 直接表达职责，并校验 PR rule / post-main / manual 三类职责边界。

## 范围

- **命名规范**：01. App Pipeline → 08. Deploy Gamma ECS
- **职责边界**：PR rule（03/04/05）、post-main（02/07）、manual（01/06/08）
- **02/03 去重检查**：确认 Service Pipeline 与 Delivery Gate 职责互补、无冗余执行

## 适用范围与约束

- **适用**：deliver-deploy-prod-pipeline 下所有 workflow；与 `workflow_consolidation_plan.md` 对齐
- **约束**：不得保留重复名称（如 05/05b、08b/08b）或依赖旧的 `workflow_run` 定时合流链
- **不适用**：非 workflow 命名、与主干治理无关的业务设计

## 与父/子节点关系

**父节点**：deliver-deploy-prod-pipeline（L2）

| 关联节点 | 说明 |
|----------|------|
| integration-deploy-and-l3-l4-gate | 含 04. Pre-Release Gate |
| gray-release-to-prod | 含 06/07 Deploy To Prod |

## 验收标准概要

- A1：主工作流名称唯一且符合 01～08 序号
- A2：`workflow_consolidation_plan.md` 含最新命名规范与 02/03 去重结论
- A3：不存在 `merge-dev1.0-to-main.yml`、`05 wrapper` 等历史重复入口
- A4：`ci_cd_end_to_end_design.md`、`deliver_to_production_runbook.md`、`branch_strategy.md` 与规范一致
