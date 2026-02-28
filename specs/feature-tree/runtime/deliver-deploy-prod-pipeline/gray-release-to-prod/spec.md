# L3 特性：gray-release-to-prod

## 功能说明

G5c 灰度到生产：在 pre-release-gate 通过后，将构建物按**可配置阶段**灰度部署到 prod，支持半自动（workflow_dispatch）与全自动（pre-release 触发）两种模式。

## 范围

- **阶段划分**：初始灰度（Stage 1）+ Carry-on 滚动（Stage 2+）
- **Stage 1 初始灰度**：全自动 deploy → SLO；部署 pod 数可配置（当前 2 副本下为 1 pod）
- **Stage 2 Carry-on**：直接到 100%；需人工审批后 deploy → SLO
- **配置驱动**：`gray_rollout_stages.yaml` 声明各阶段 replicas 与 auto 标志，随副本增加可扩展中间阶段
- **已有能力**：`config_release_gray_rollout.sh`、`config_release_slo_gate.sh`、`config_release_rollback.sh` 已支持 STEP 5/25/50/100

## 适用范围与约束

- **适用**：首次上线、2 副本；随用户增长可扩展为 4、8 副本等多阶段
- **约束**：STEP 与脚本沿用 5/25/50/100；`STEP = (目标 replicas / total_replicas) * 100`
- **不适用**：非 K8s 部署、非滚动发布场景
- **前置**：pre-release-gate 已通过（L1+L2 → deploy integration → L3 → L4）

## 与父/子节点关系

**父节点**：deliver-deploy-prod-pipeline（L2）

| 子节点 | 职责 | 优先级 |
|--------|------|--------|
| **config-rollout-slo-gate** | 单步 rollout 状态 + SLO 决策 + 回滚脚本 | 优先 |

## 验收标准概要

- A1：初始灰度（1 pod）可全自动执行，SLO 通过后进入 Carry-on 审批
- A2：Carry-on 100% 需人工审批（Environment approval 或 workflow_dispatch 续跑）
- A3：`gray_rollout_stages.yaml` 可配置 replicas 与 auto，workflow 按配置计算 STEP
- A4：半自动 workflow_dispatch 支持 step 50 → 100（2 副本）
- A5：deliver_to_production_runbook 与 deploy_prod_design 一致
