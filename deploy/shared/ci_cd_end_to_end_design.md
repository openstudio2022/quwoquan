# CI/CD 端到端闭环落实方案

> 目标：deliver 入库 → 部署 integration → L3/L4 验证 → 灰度 prod 全链路自动化或半自动化

**当前部署目标**：CI/CD 仅考虑**阿里云 ACK** 部署。pre-release-gate、service_pipeline 使用 `CLOUD_PROVIDER=aliyun` 和 `deploy/kustomization/aliyun-integration`、`deploy/kustomization/aliyun-prod`。

---

## 1. 当前 CI/CD 现状

### 1.1 已有 Workflows（与 specs/00_MASTER_DEVELOPMENT_FLOW 阶段对应）

| Workflow | 触发 | 职责 | 对应阶段 |
|----------|------|------|----------|
| `delivery-gate.yml` | PR / push main, dev1.0 | 拓扑校验、L1+L2 质量门（PR/入库阶段） | G0~G3 |
| `service_pipeline.yml` | quwoquan_service/**、deploy/** | Go 构建、rec-model 镜像、kustomize 校验（无 L2） | G2 |
| `app_pipeline.yml` | quwoquan_app/** | Flutter analyze；v* tag → macOS 构建（无 L1） | G2 / 发布 |
| `pre-release-gate.yml` | v*-rc* tag、手动 | gate(L1+L2) → deploy → L3 → L4 | G3→G5b |

### 1.2 当前 pre-release 链路（已实现）

```
v*-rc* tag
  → gate: make gate（L1+L2）+ kustomize build（G3）
  → deploy-integration: kubectl apply（G5a，需 INTEGRATION_KUBECONFIG）
  → l3-api-contract: make test-api-contract（G5b，部署完成后）
  → l4-android / l4-ios: Firebase Test Lab（G5b，部署完成后）
```

**已落实**：gate 仅 L1+L2；L3/L4 必须等待 deploy-integration 完成后执行，验证真实部署环境。

---

## 2. 端到端闭环目标（已落实）

```
deliver 入库(main)
    ↓
v*-rc* tag（或 main 合并后自动打 tag）
    ↓
pre-release-gate
    │
    ├─ Job1: gate（L1+L2）
    ├─ Job2: deploy-integration（kubectl apply）  ✓ 已实现
    ├─ Job3: l3-api-contract（需 Job2 完成）      ✓ 已实现
    ├─ Job4: l4-android（需 Job2 完成）           ✓ 已实现
    └─ Job5: l4-ios（需 Job2 完成）               ✓ 已实现
    ↓
全部通过 → 允许灰度到 prod（人工或下游 workflow）
    ↓
config-gray-rollout / config-slo-gate / config-rollback
```

---

## 3. 落实方案（3.1、3.2 已实现于 pre-release-gate.yml）

### 3.1 deploy-integration Job（已实现）

**职责**：将 kustomize 构建的 manifest 应用到 integration K8s 集群。

**前置**：
- integration 集群已创建（阿里云 ACK / 火山引擎 VKE / 华为云 CCE）
- GitHub Secrets 配置：
  - `INTEGRATION_KUBECONFIG`：integration 集群 kubeconfig（base64 编码）
  - 或使用 OIDC：`INTEGRATION_CLUSTER_NAME`、云厂商 OIDC（阿里云 OIDC、GCP Workload Identity 等）

**实现要点**：
```yaml
deploy-integration:
  name: G5a Deploy to integration
  needs: [gate]
  runs-on: ubuntu-latest
  env:
    KUBECONFIG: ${{ secrets.INTEGRATION_KUBECONFIG }}
  steps:
    - uses: actions/checkout@v4
    - uses: syntaqx/setup-kustomize@v1
    - run: |
        # 可选：安装 kubectl
        curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
        chmod +x kubectl && sudo mv kubectl /usr/local/bin/
      # 若使用 OIDC，此处改为 cloud provider 的 configure-credentials action
    - name: Apply to integration
      run: |
        CLOUD_PROVIDER=${CLOUD_PROVIDER:-aliyun}
        kustomize build deploy/kustomization/${CLOUD_PROVIDER}-integration | \
          kubectl apply -f - --server-side
    - name: Wait for rollout
      run: kubectl rollout status deployment/seed-box -n seed-box-integration --timeout=5m
    - name: Health check
      run: |
        # 可选：curl $STAGING_BASE_URL/health
        kubectl get pods -n seed-box-integration
```

**多云**：通过 `CLOUD_PROVIDER` 选择 kustomization 文件；不同云需要不同 KUBECONFIG 或 OIDC 配置。

---

### 3.2 L3 / L4 依赖 deploy-integration（已实现）

**现状**：`l3-api-contract`、`l4-android`、`l4-ios` 均已 `needs: [gate, deploy-integration]`，integration 部署完成后再跑 L3/L4。

---

### 3.3 灰度到 prod（G5c）

**现状**：`config-gray-rollout`、`config-slo-gate`、`config-rollback` 脚本已存在，需人工执行或单独 workflow 触发。

**落实方式**：
1. **人工**：pre-release 全通过后，运维执行 `make config-gray-rollout ...`
2. **半自动**：新增 `deploy-prod-gray.yml` workflow，`workflow_dispatch` 触发，输入 STEP/版本/SLO 等，单步灰度 + SLO 卡点（详见 `deploy/shared/deploy_prod_design.md`）
3. **全自动**：pre-release 通过后自动触发灰度；**初始灰度**（1 pod 可配置，全自动）→ **Carry-on 100%**（需人工审批）；SLO 从监控拉取；随副本增加可扩展阶段（详见 `deploy/shared/deploy_prod_design.md`）

**建议**：先人工，待流程稳定后演进到半自动，再视需要上全自动。

---

## 4. 依赖与前置

### 4.1 GitHub Secrets（必须）

| Secret | 用途 |
|--------|------|
| `STAGING_BASE_URL` | integration API 地址，L3/L4 使用 |
| `STAGING_TEST_AUTH_TOKEN` | L3/L4 鉴权（对应 env TEST_AUTH_TOKEN） |
| `INTEGRATION_KUBECONFIG` | integration 集群 kubeconfig（或 OIDC 等效） |
| `GCP_SERVICE_ACCOUNT_KEY` | FTL 用 |
| `FTL_RESULTS_BUCKET` | FTL 结果存储 |
| `MATCH_PASSWORD` | iOS 签名（如需要） |

### 4.2 基础设施

- **integration 集群**：K8s 集群（阿里云/火山/华为云），namespace `seed-box-integration`
- **镜像仓库**：kustomization 中 `images` 指向的 registry 可被集群拉取
- **ConfigMap/Secret**：CONFIG_VERSION、IMAGE_VERSION 等与 kustomize overlay 一致

### 4.3 版本注入

当前 integration overlay 使用 `v2026.02.28.0` 等硬编码。pre-release tag 触发时，需要：
- 从 tag 解析版本（如 `v1.0.0-rc.1` → `v1.0.0.rc1`）
- 通过 kustomize `replacements` 或 `sed` 注入到 manifest
- 或使用 CI 变量 `IMAGE_VERSION`、`CONFIG_VERSION` 覆盖

---

## 5. 实施顺序（1~4 已完成）

| 步骤 | 动作 | 状态 |
|------|------|------|
| 1 | 配置 `INTEGRATION_KUBECONFIG`（或 OIDC） | ✓ 按需 |
| 2 | `deploy-integration` job（kubectl apply） | ✓ 已实现 |
| 3 | L3/L4 job 依赖 `deploy-integration` | ✓ 已实现 |
| 4 | `l3-api-contract` job（deploy 后执行） | ✓ 已实现 |
| 5 | 版本注入（tag → CONFIG/IMAGE_VERSION） | P1 待做 |
| 6 | 灰度 workflow（workflow_dispatch 半自动） | P2 待做 |

---

## 6. 参考

- `deploy/shared/deliver_to_production_runbook.md` — 端到端运行手册
- `.github/workflows/pre-release-gate.yml` — 当前 pre-release 流程
- `scripts/deploy_to_integration.sh` — 构建脚本（需扩展或新建 apply 脚本）
- `specs/feature-tree/runtime/deliver-deploy-prod-pipeline/design.md` — 设计
