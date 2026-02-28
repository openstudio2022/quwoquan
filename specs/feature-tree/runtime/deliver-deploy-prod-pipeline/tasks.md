# 开发任务：deliver-deploy-prod-pipeline

## 总览（执行顺序）

```
metadata → codegen → 业务逻辑 → 测试
```

本 L2 以流程/CI/部署为主，metadata 变更少；codegen 若有则跟随 metadata。

---

## 当前交付任务

### M — Metadata（可选）

| 任务 | 说明 | 状态 |
|------|------|------|
| M1 | 扩展 `deploy/shared/process_domain_mapping.yaml` 支持 cloud_provider 字段（若需显式声明每环境目标云） | 待评估 |
| M2 | 新增 `deploy/shared/cloud_provider_config.yaml`（可选）：云厂商 registry、LB annotation 模板等 | 待评估 |

### C — Codegen（若有 M1/M2）

| 任务 | 说明 | 状态 |
|------|------|------|
| C1 | 若 M 有产出，codegen 部署校验脚本或 schema | 待评估 |

### T — 业务逻辑 / 流水线

| 任务 | 说明 | 状态 |
|------|------|------|
| T1 | 创建 `deploy/cloud-providers/aliyun/seed-box/overlays/{integration,prod}`，复用 base，注入阿里云特定 patch | 待执行 |
| T2 | 创建 `deploy/cloud-providers/volcengine/seed-box/overlays/{integration,prod}`，火山引擎特定 patch | 待执行 |
| T3 | 创建 `deploy/cloud-providers/huaweicloud/seed-box/overlays/{integration,prod}`，华为云特定 patch | 待执行 |
| T4 | 编写 `scripts/deploy_to_integration.sh`，支持 `CLOUD_PROVIDER` 参数，调用 kustomize 构建并 apply | 待执行 |
| T5 | 创建 `.github/workflows/pre-release-gate.yml`：v*-rc* 触发 gate-full → deploy integration → L3 → L4，全部通过输出「可灰度」 | 待执行 |
| T6 | 串联 daily-api-contract、e2e.yaml 与 pre-release-gate（或合并为统一 pre-release workflow） | 待执行 |
| T7 | 更新 `deploy/shared/deliver_to_production_runbook.md`，增加多云切换步骤与 `CLOUD_PROVIDER` 说明 | 待执行 |
| T8 | 更新 Makefile：`deploy-integration CLOUD_PROVIDER=aliyun\|volcengine\|huaweicloud` | 待执行 |

### V — 测试 / 验证

| 任务 | 说明 | 状态 |
|------|------|------|
| V1 | 验证 `kustomize build deploy/cloud-providers/aliyun/seed-box/overlays/integration` 无错误 | 待执行 |
| V2 | 验证 `kustomize build deploy/cloud-providers/volcengine/seed-box/overlays/integration` 无错误 | 待执行 |
| V3 | 验证 `kustomize build deploy/cloud-providers/huaweicloud/seed-box/overlays/integration` 无错误 | 待执行 |
| V4 | 在至少一云（如阿里云）上执行端到端：deliver → deploy integration → L3 → L4 → 灰度 prod | 待执行 |
| V5 | 演练多云切换：同一 manifest 在阿里云与火山引擎分别渲染，确认无硬编码云厂商路径 | 待执行 |

---

## 搁置任务（带规划）

| 任务 | 搁置原因 | 计划重启条件 |
|------|----------|--------------|
| Argo CD / GitOps 集成 | 当前以脚本 + GitHub Actions 为主 | 引入 K8s 多集群或 GitOps 规范时 |
| 腾讯云 / AWS 支持 | 当前优先三云（阿里云、火山引擎、华为云） | 有明确多云需求时 |
| 云厂商 ConfigCenter 集成 | 依赖各云 ConfigCenter 开通与 API | 配置下发需从云侧拉取时 |

---

## 未来演进任务

- Argo CD ApplicationSet 管理多云多集群
- 跨云容灾与故障切换
- 更多云（腾讯云 TKE、AWS EKS）按 `cloud-providers/` 模式扩展
