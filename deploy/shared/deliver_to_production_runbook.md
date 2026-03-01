# Deliver → Prod 端到端运行手册

## 1. 目标

从特性到入库（L1/L2 自测通过），再到集成验证（L3/L4），再到生产端到端打通，含灰度/滚动发布。

```
特性 → deliver 入库(L1/L2) → deploy 到 integration → L3/L4 验证 → 灰度到 prod
```

---

## 2. 阶段划分

| 阶段 | 命令/动作 | 门禁 | 输出 |
|------|-----------|------|------|
| 1. 开发+入库 | `/opsx-deliver` | G2 → G3 → G4 | 代码入库 main，L1/L2 通过 |
| 2. 部署 integration | CI/CD 或手动 | G5a | integration 环境运行目标版本 |
| 3. 集成验证 | L3 + L4 测试 | G5b | L3/L4 通过 |
| 4. 灰度到 prod | `config-gray-rollout` | G5c | prod 灰度完成，SLO 通过 |

---

## 3. 前置条件

### 3.1 Deliver 阶段完成

- 代码已合入 main
- `make gate` 通过（L1a+b+c + L2）。**AI 编程助手提交前必须自动执行 L1+L2 门禁**，不得跳过；见 `.cursor/commands/submit-with-gate.md`
- `deploy/shared/process_domain_mapping.yaml` 合法，`verify_deployment_domain_mapping.sh` 通过

### 3.2 部署环境

- **integration**：staging API 可访问，`STAGING_BASE_URL`、`TEST_AUTH_TOKEN` 已配置
- **prod**：K8s 集群就绪（阿里云 ACK / 火山引擎 VKE / 华为云 CCE），`CONFIG_VERSION`、`IMAGE_VERSION` 已确定
- **多云切换**：通过 `CLOUD_PROVIDER=aliyun|volcengine|huaweicloud` 选择 overlay，见 `deploy/cloud-providers/`

### 3.3 灰度参数

- `FROM_IMAGE`、`TO_IMAGE`：当前与目标镜像版本
- `FROM_CONFIG`、`TO_CONFIG`：当前与目标配置版本
- `STEP`：当前 2 副本为 50（初始灰度 1 pod，全自动）→ 100（Carry-on 全量，需审批）。初始灰度 pod 数可配置；副本增加时可扩展中间阶段。

---

## 4. G5a：部署到 integration

1) 选择云厂商并渲染 deployment（入口：`deploy/kustomization/`）：

```bash
# 阿里云（默认）
CLOUD_PROVIDER=${CLOUD_PROVIDER:-aliyun}
kustomize build deploy/kustomization/${CLOUD_PROVIDER}-integration

# 或 make deploy-integration
make deploy-integration [CLOUD_PROVIDER=volcengine]
```

2) 应用部署（按实际 CI/CD 或 ArgoCD 流程）

3) 验证 integration 可达：

```bash
curl -s -o /dev/null -w "%{http_code}" $STAGING_BASE_URL/health
```

---

## 5. G5b：L3/L4 集成验证

### 5.1 L3 API Contract

```bash
STAGING_BASE_URL=<integration-api-url> TEST_AUTH_TOKEN=<token> make test-api-contract
```

失败 → 不得进入 G5c。

### 5.2 L4 Patrol（真机/模拟器）

```bash
cd quwoquan_app && patrol test test/patrol/ \
  --dart-define=ENV=staging \
  --dart-define=STAGING_BASE_URL=<integration-api-url> \
  --dart-define=TEST_AUTH_TOKEN=<token>
```

CI 可用 `.github/workflows/pre-release-gate.yml` 在 Firebase Test Lab 执行 L4（Android + iOS）。

失败 → 不得进入 G5c。

---

## 6. G5c：灰度/滚动发布到 prod

### 6.1 灰度步进

每步执行：

```bash
make config-gray-rollout \
  SERVICE=<service> \
  FROM_IMAGE=<old> TO_IMAGE=<new> \
  FROM_CONFIG=<old> TO_CONFIG=<new> \
  STEP=50  # 初始灰度（1 pod，全自动）；100 为 Carry-on 全量（需审批）
```

### 6.2 SLO 卡点（每步后）

```bash
make config-slo-gate \
  ERROR_RATE=<实测> P95_MS=<实测> REDIS_ERROR_RATE=<实测>
```

阈值见 `deploy/service/config-release/slo_thresholds.yaml`。

### 6.3 异常回滚

```bash
make config-rollback SERVICE=<service> TO_CONFIG=<rollback-version>
```

### 6.4 high_risk_fields

变更 `deploy/service/config-release/high_risk_fields.yaml` 中字段时，须：

- 审批（min_approvers: 2）
- 灰度（require_gray_release: true）
- 回滚方案（require_rollback_plan: true）

---

## 7. 端到端检查清单

```
☐ deliver 完成，代码已入库 main
☐ make gate 通过（L1+L2）
☐ verify_deployment_domain_mapping.sh 通过
☐ integration 已部署目标版本
☐ L3 test-api-contract 通过
☐ L4 patrol 通过（或 FTL 通过）
☐ 灰度：初始灰度（1 pod，全自动）→ Carry-on 100%（审批后执行）
☐ 每步 SLO 卡点通过
☐ prod 100% 后监控稳定
```

---

## 8. 参考

- `specs/00_MASTER_DEVELOPMENT_FLOW.md` — 主流程（含 Deploy 阶段 G5）
- `deploy/shared/ci_cd_end_to_end_design.md` — **CI/CD 端到端闭环落实方案**（pre-release workflow、secrets、实施顺序）
- `deploy/shared/workflow_consolidation_plan.md` — **Workflow 命名规范**（01～06、02/03 去重）
- `.cursor/commands/opsx-deploy.md` — 部署命令
- `deploy/shared/process_domain_mapping_runbook.md` — 部署拓扑
- `deploy/service/config-release/runbook.md` — 配置发布与灰度
- `specs/feature-tree/runtime/deliver-deploy-prod-pipeline/design.md` — 多云（阿里云/火山引擎/华为云）设计
