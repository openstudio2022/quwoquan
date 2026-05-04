# CI/CD 端到端闭环落实方案

> 目标：进入 `main` 前完成 merge queue 阻断验证；进入 `main` 后再执行发布后续动作。

**当前部署目标**：CI/CD 仅考虑**阿里云 ACK** 部署。pre-release-gate、service_pipeline 使用 `CLOUD_PROVIDER=aliyun` 和 `deploy/kustomization/aliyun-integration`、`deploy/kustomization/aliyun-prod`。

**五环境总览**（alpha / beta / gamma / prod-gray / prod、波次关系）：见 **[environment_matrix.md](environment_matrix.md)**。

---

## 1. 当前 CI/CD 现状

### 1.1 已有 Workflows（与 specs/00_MASTER_DEVELOPMENT_FLOW 阶段对应）

命名规范见 `deploy/shared/workflow_consolidation_plan.md` §2；02/03 去重见 §4.6。

| Workflow 名称 | 文件 | 触发 | 职责 | 对应阶段 |
|---------------|------|------|------|----------|
| 03. Delivery Gate | `delivery-gate.yml` | `merge_group`、手动 | merge queue 快速主门禁：拓扑校验、L1+L2 | G0~G3 |
| 05. App Env Device Matrix | `app-env-device-matrix-self-hosted.yml` | `merge_group`、`workflow_call`、手动 | self-hosted 设备矩阵；动态发现当前 Mac 上全部移动设备 | G3/G5b |
| 04. Pre-Release Gate | `pre-release-gate.yml` | `merge_group`、手动 | deploy integration → L3 → L4 → gamma smoke | G3→G5b |
| 02. Service Pipeline | `service_pipeline.yml` | `push main`、手动 | main 后 Go 构建、rec-model 镜像、kustomize prod 校验 | G2 / post-main |
| 07. Deploy To Prod (Auto) | `deploy-prod-auto.yml` | `push main`、手动 | main 后自动推进 prod 占位链路 | G5c |
| 01. App Pipeline | `app_pipeline.yml` | `v*` tag、手动 | 端侧发布构建（macOS） | 发布 |
| 06. Deploy To Prod (Gray) | `deploy-prod-gray.yml` | 手动 | 半自动灰度 | G5c |
| 08. Deploy Gamma ECS | `deploy-gamma-ecs.yml` | 手动 | gamma / onebox 发布与复验 | G5a→G5b |

### 1.2 当前 pre-release 链路（已实现）

```text
merge queue(main)
  → 03 Delivery Gate（L1+L2）
  → 05 App Env Device Matrix（alpha/beta self-hosted）
  → 04 Pre-Release Gate（deploy integration → L3 → L4 → gamma smoke）
  → 全绿后才允许进入 main
```

**已落实**：`03/04/05` 都不再响应分支 push；merge queue 是唯一主干阻断路径。

### 1.3 ECS Onebox（gamma 镜像栈，`deploy-gamma-ecs.yml`）

与 ACK integration **并行**的一条闭环：**08** 已改成**纯手动** onebox / gamma 演练链路；merge queue 主路径不再在 `main` 后重复触发这套重验证。部署前后在远端 `../gamma-backups/` 备份 tarball，结构化报告见 `artifacts/ecs-onebox/deploy-report.json`，回滚见 **`ecs-onebox-rollback.yml` / `scripts/rollback_gamma_ecs.sh`**。

---

## 2. 端到端闭环目标（已落实）

**分支策略**：支持 `dev1.0` 分支开发与 trunk development 两种模式，但**进入 `main` 的唯一门禁都是 merge queue**，见 `deploy/shared/branch_strategy.md`。

```text
feature / dev1.0
  → 用户显式发起到 main 的 PR
  → merge queue
      ├─ 03 Delivery Gate
      ├─ 05 App Env Device Matrix
      └─ 04 Pre-Release Gate
  → 全部通过后进入 main
  → main post-merge:
      ├─ 02 Service Pipeline
      └─ 07 Deploy To Prod (Auto)
```

---

## 3. 落实方案（3.1、3.2 已实现于 pre-release-gate.yml）

### 3.1 deploy-integration Job（已实现）

**职责**：将 kustomize 构建的 manifest 应用到 integration K8s 集群。

**前置**：
- integration 集群已创建（阿里云 ACK / 火山引擎 VKE / 华为云 CCE）
- GitHub Secrets 配置（与 [`.github/workflows/pre-release-gate.yml`](../../.github/workflows/pre-release-gate.yml) 一致）：
  - **`GAMMA_KUBECONFIG`**：integration 集群 kubeconfig（**base64 编码**）。未设置时 workflow 跳过 `kubectl apply`，仅打印 warning。
  - 先前文档中的 `INTEGRATION_KUBECONFIG` 名称已弃用；请以 workflow 实际读取的 **`GAMMA_KUBECONFIG`** 为准。
  - 或使用 OIDC：可在 job 内改为云厂商 `configure-credentials` + `kubectl`（需自行替换 shell 片段）。

**实现要点**（与当前 `pre-release-gate.yml` 语义对齐）：
```yaml
deploy-integration:
  name: G5a Deploy to integration
  runs-on: ubuntu-latest
  env:
    GAMMA_KUBECONFIG: ${{ secrets.GAMMA_KUBECONFIG }}
  steps:
    - uses: actions/checkout@v4
    - uses: syntaqx/setup-kustomize@v1
    - run: |
        curl -sLO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
        chmod +x kubectl && sudo mv kubectl /usr/local/bin/
    - name: Apply to integration
      run: |
        if [ -z "$GAMMA_KUBECONFIG" ]; then echo "skip apply"; exit 0; fi
        mkdir -p ~/.kube && echo "$GAMMA_KUBECONFIG" | base64 -d > ~/.kube/config
        kustomize build deploy/kustomization/${CLOUD_PROVIDER}-integration | kubectl apply -f - --server-side
    - name: Wait for rollout
      run: kubectl rollout status deployment/seed-box -n seed-box-integration --timeout=5m
```

**多云**：通过 `CLOUD_PROVIDER` 选择 kustomization 文件；不同云需要不同 KUBECONFIG 或 OIDC 配置。

---

### 3.2 L3 / L4 依赖 deploy-integration（已实现）

**现状**：`l3-api-contract`、`l4-mobile-self-hosted` 与 `app-assistant-runtime-gamma` 均已依赖 `deploy-integration`，integration 部署完成后再跑 L3/L4/gamma smoke。

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
| `GAMMA_BASE_URL` | gamma API 基址，L3/L4 使用 |
| `GAMMA_PRODUCT_OPS_BASE_URL` | gamma 上 Ops/产品面 API 基址，`make test-api-contract` 必需 |
| `GAMMA_TEST_AUTH_TOKEN` | L3/L4 鉴权 |
| `GAMMA_KUBECONFIG` | **integration** 集群 kubeconfig（base64）；`pre-release-gate.yml` 中 `deploy-integration` 使用；可选，缺省则跳过 apply |

完整矩阵（含 `03/04/05/06/07/08`、Variables、self-hosted）见 **[environment_matrix.md §3](environment_matrix.md)**。

### 4.2 基础设施

- **integration 集群**：K8s 集群（阿里云/火山/华为云），namespace `seed-box-integration`；`pre-release-gate.yml` 中 `kubectl rollout status deployment/seed-box -n seed-box-integration` 与 [`deploy/service/seed-box/kustomize/overlays/integration`](../../deploy/service/seed-box/kustomize/overlays/integration) 一致（若改名 overlay，须同步改 workflow）。
- **镜像仓库**：kustomization 中 `images` 指向的 registry 可被集群拉取
- **ConfigMap/Secret**：CONFIG_VERSION、IMAGE_VERSION 等与 kustomize overlay 一致

### 4.3 Self-hosted Runner（05 / 08 / pre-release L4）

`app-env-device-matrix-self-hosted.yml` 要求：

- **Runner**：统一使用当前开发机注册的 `self-hosted` + `macOS` runner。
- **设备发现**：通过 `flutter devices --machine` 动态发现当前可见 Android/iOS 模拟器与真机。
- **执行语义**：发现到的每台设备都会逐台执行；只要总设备数 >= 1 即可进入矩阵，不再依赖自定义 runner label 或固定 device id。

若当前 Mac 上暂时只连着 iPhone、只开了 Android Emulator，或两者同时存在，workflow 都会按实际发现结果展开；某一平台没有设备时会被跳过，但总设备数为 0 时直接 `gate_block`。

### 4.4 merge queue / main 后验证清单

1. **merge queue required checks**：确认 `03`、`04`、`05` 都作为 required checks 配置在 `main` 分支保护 / merge queue 中。
2. **03 Delivery Gate**：确认 merge queue run 成功。
3. **04 Pre-Release Gate**：确认 `deploy-integration`、`l3`、`l4`、`assistant-runtime-gamma`、`release-evidence-summary` 全绿。
4. **05 App Env Device Matrix**：确认当前 Mac 可见设备被正确发现，且至少一台设备执行成功。
5. **07 Deploy To Prod (Auto)**：确认 main 合入后触发成功；`production` Environment 若启用审批，在 GitHub 上完成 Stage 2 审批。
6. **08 Deploy Gamma ECS**：仅在需要 onebox / gamma 手动演练时通过 `workflow_dispatch` 触发。

### 4.5 版本注入

当前 integration overlay 使用 `v2026.02.28.0` 等硬编码。pre-release tag 触发时，需要：
- 从 tag 解析版本（如 `v1.0.0-rc.1` → `v1.0.0.rc1`）
- 通过 kustomize `replacements` 或 `sed` 注入到 manifest
- 或使用 CI 变量 `IMAGE_VERSION`、`CONFIG_VERSION` 覆盖

---

## 5. 实施顺序（1~4 已完成）

| 步骤 | 动作 | 状态 |
|------|------|------|
| 1 | 配置 `GAMMA_KUBECONFIG`（integration kubeconfig，base64）或 OIDC | ✓ 按需 |
| 2 | `deploy-integration` job（kubectl apply） | ✓ 已实现 |
| 3 | L3/L4 job 依赖 `deploy-integration` | ✓ 已实现 |
| 4 | `l3-api-contract` job（deploy 后执行） | ✓ 已实现 |
| 5 | 版本注入（tag → CONFIG/IMAGE_VERSION） | P1 待做 |
| 6 | 灰度 workflow（workflow_dispatch 半自动） | P2 待做 |

---

## 6. 参考

- `deploy/shared/environment_matrix.md` — 五环境矩阵、STAGING=integration 语义、各环境验证命令
- `deploy/shared/branch_strategy.md` — 分支策略（显式 PR + merge queue）
- `deploy/shared/deliver_to_production_runbook.md` — 端到端运行手册
- `.github/workflows/pre-release-gate.yml` — 当前 pre-release 流程
- `scripts/deploy_to_integration.sh` — 构建脚本（需扩展或新建 apply 脚本）
- `specs/feature-tree/runtime/deliver-deploy-prod-pipeline/design.md` — 设计
