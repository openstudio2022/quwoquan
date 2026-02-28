# 开发任务：gray-release-to-prod

## 总览（执行顺序）

```
metadata → codegen → 业务逻辑 → 测试
```

本 L3 以部署配置与 workflow 为主，metadata 变更少；codegen 若有则跟随 metadata。

---

## 当前交付任务

- [x] M2 更新 deploy_prod_design 与 runbook 引用 gray_rollout_stages
- [x] M1 新增 gray_rollout_stages.yaml（基线化已完成）
- [x] T1 新增 deploy-prod-gray.yml workflow
- [x] T2 新增 deploy-prod-auto 或 pre-release-gate 内 gray-initial/gray-carry-on job
- [x] T3 prepare job 读取 gray_rollout_stages 计算 STEP
- [x] T4 补齐 PROD_KUBECONFIG、prod apply 脚本
- [x] V1 验证 gray_rollout_stages 解析
- [x] V2 验证 deploy-prod-gray workflow dry_run
- [ ] V3 端到端演练（需集群）

### M — Metadata / 配置

| 任务 | 说明 | 状态 |
|------|------|------|
| M1 | 新增 `deploy/shared/gray_rollout_stages.yaml`：声明 stages（replicas, auto），当前 2 副本为 initial(1)+full(2) | [x] 已完成 |
| M2 | 更新 `deploy/shared/deploy_prod_design.md` 与 runbook 引用 gray_rollout_stages | [x] 已完成 |

### C — Codegen（若有）

| 任务 | 说明 | 状态 |
|------|------|------|
| C1 | 无 codegen 依赖 | 跳过 |

### T — 流水线 / Workflow

| 任务 | 说明 | 状态 |
|------|------|------|
| T1 | 新增 `deploy-prod-gray.yml`（workflow_dispatch）：单步灰度 + 手填 SLO；step 50/100 支持 | [x] 已完成 |
| T2 | 新增 `deploy-prod-auto.yml` 或 pre-release-gate 内 job：gray-initial（STEP=50 全自动）→ gray-carry-on（STEP=100 需 Environment approval） | [x] 已完成 |
| T3 | prepare job 读取 gray_rollout_stages，计算 initial STEP 与 full STEP | [x] 已完成 |
| T4 | 补齐 PROD_KUBECONFIG、prod kustomize apply 脚本（若当前仅有 state 更新） | [x] 已完成 |

### V — 测试 / 验证

| 任务 | 说明 | 状态 |
|------|------|------|
| V1 | 验证 gray_rollout_stages 解析无错误 | [x] 已完成 |
| V2 | 验证 deploy-prod-gray workflow 可手动触发（dry_run） | [x] 已完成 |
| V3 | 端到端：pre-release 通过 → 初始灰度自动 → Carry-on 审批后 100% | 待执行（需集群） |

---

## 搁置任务（带规划）

| 任务 | 搁置原因 | 计划重启条件 |
|------|----------|--------------|
| Argo CD / Progressive Delivery | 当前以脚本 + GitHub Actions 为主 | 引入 GitOps 或 Argo Rollouts 时 |
| SLO 自动从 Prometheus 拉取 | 需监控 API 与查询语句约定 | 监控就绪、有明确指标名时 |
| 多副本中间阶段（如 1→2→4） | 当前 2 副本，仅 1→2 | 副本增加到 4+ 时 |

---

## 未来演进任务

- 4 副本时扩展 gray_rollout_stages 为 1→2→4，每阶段 auto 可配
- Argo Rollouts 或 Flagger 替代脚本灰度
- SLO 自动拉取与 slo-gate 集成
