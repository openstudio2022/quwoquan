# CI/CD 端到端闭环落实方案

> 目标：deliver 入库 → 部署 integration → L3/L4 验证 → 灰度 prod 全链路自动化或半自动化

**当前部署目标**：CI/CD 仅考虑**阿里云 ACK** 部署。pre-release-gate、service_pipeline 使用 `CLOUD_PROVIDER=aliyun` 和 `deploy/kustomization/aliyun-integration`、`deploy/kustomization/aliyun-prod`。

**五环境总览**（alpha / beta / gamma / prod-gray / prod、波次关系）：见 **[environment_matrix.md](environment_matrix.md)**。

---

## 1. 当前 CI/CD 现状

### 1.1 已有 Workflows（与 specs/00_MASTER_DEVELOPMENT_FLOW 阶段对应）

命名规范见 `deploy/shared/workflow_consolidation_plan.md` §2；02/03 去重见 §4.6。

| Workflow 名称 | 文件 | 触发 | 职责 | 对应阶段 |
|---------------|------|------|------|----------|
| 03. Delivery Gate | `delivery-gate.yml` | PR / push main, dev1.0 | 拓扑校验、L1+L2 质量门（PR/入库阶段） | G0~G3 |
| 02. Service Pipeline | `service_pipeline.yml` | quwoquan_service/**、deploy/** | Go 构建、rec-model 镜像、kustomize 校验（无 L2） | G2 |
| 01. App Pipeline | `app_pipeline.yml` | quwoquan_app/** | Flutter analyze；v* tag → macOS 构建（无 L1） | G2 / 发布 |
| 04. Pre-Release Gate | `pre-release-gate.yml` | v*-rc* tag、push to main（日节奏）、手动 | gate(L1+L2) → deploy → L3 → L4 | G3→G5b |
| 07. Merge dev1.0 To Main | `merge-dev1.0-to-main.yml` | 定时 6:00、workflow_dispatch | merge dev1.0 → main | 日节奏 |

### 1.2 当前 pre-release 链路（已实现）

```
v*-rc* tag
  → gate: make gate（L1+L2）+ kustomize build（G3）
  → deploy-integration: kubectl apply（G5a，需 INTEGRATION_KUBECONFIG）
  → l3-api-contract: make test-api-contract（G5b，部署完成后）
  → l4-android / l4-ios: GitHub hosted Android Emulator / iOS Simulator（G5b，部署完成后）
```

**已落实**：gate 仅 L1+L2；L3/L4 必须等待 deploy-integration 完成后执行，验证真实部署环境。

### 1.3 ECS Onebox（gamma 镜像栈，`deploy-gamma-ecs.yml`）

与 ACK integration **并行**的一条闭环：**hosted 仅负责 gate + 源码打包**；**self-hosted** 负责 **alpha/beta 预检矩阵**、**alpha/beta/gamma 发布准入矩阵** 与 prod 后 **gamma 烟测**；**ECS** 在同一机器同端口执行 **pre 全量部署** 与 **prod 就地升级**（`GAMMA_ECS_SKIP_UPLOAD`）。部署前后在远端 `../gamma-backups/` 备份 tarball，结构化报告见 `artifacts/ecs-onebox/deploy-report.json`，回滚见 **`ecs-onebox-rollback.yml` / `scripts/rollback_gamma_ecs.sh`**。

---

## 2. 端到端闭环目标（已落实）

**分支策略**：日常 PR 合入 dev1.0；main 仅由定时 merge 更新，见 `deploy/shared/branch_strategy.md`。

```
deliver 入库(dev1.0) → 定时 merge → main
    ↓
v*-rc* tag 或 push to main（日节奏 merge 后）
    ↓
pre-release-gate
    │
    ├─ Job1: gate（L1+L2）
    ├─ Job2: deploy-integration（kubectl apply）  ✓ 已实现
    ├─ Job3: l3-api-contract（需 Job2 完成）      ✓ 已实现
    ├─ Job4: l4-android（GitHub hosted emulator，需 Job2 完成） ✓ 已实现
    └─ Job5: l4-ios（GitHub hosted simulator，需 Job2 完成）    ✓ 已实现
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
- GitHub Secrets 配置（与 [`.github/workflows/pre-release-gate.yml`](../../.github/workflows/pre-release-gate.yml) 一致）：
  - **`GAMMA_KUBECONFIG`**：integration 集群 kubeconfig（**base64 编码**）。未设置时 workflow 跳过 `kubectl apply`，仅打印 warning。
  - 先前文档中的 `INTEGRATION_KUBECONFIG` 名称已弃用；请以 workflow 实际读取的 **`GAMMA_KUBECONFIG`** 为准。
  - 或使用 OIDC：可在 job 内改为云厂商 `configure-credentials` + `kubectl`（需自行替换 shell 片段）。

**实现要点**（与当前 `pre-release-gate.yml` 语义对齐）：
```yaml
deploy-integration:
  name: G5a Deploy to integration
  needs: [gate]
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
| `GAMMA_BASE_URL` | gamma API 基址，L3/L4 使用 |
| `GAMMA_PRODUCT_OPS_BASE_URL` | gamma 上 Ops/产品面 API 基址，`make test-api-contract` 必需 |
| `GAMMA_TEST_AUTH_TOKEN` | L3/L4 鉴权 |
| `GAMMA_KUBECONFIG` | **integration** 集群 kubeconfig（base64）；`pre-release-gate.yml` 中 `deploy-integration` 使用；可选，缺省则跳过 apply |

完整矩阵（含 05 / 06 / 08、Variables、self-hosted）见 **[environment_matrix.md §3](environment_matrix.md)**。

### 4.2 基础设施

- **integration 集群**：K8s 集群（阿里云/火山/华为云），namespace `seed-box-integration`；`pre-release-gate.yml` 中 `kubectl rollout status deployment/seed-box -n seed-box-integration` 与 [`deploy/service/seed-box/kustomize/overlays/integration`](../../deploy/service/seed-box/kustomize/overlays/integration) 一致（若改名 overlay，须同步改 workflow）。
- **镜像仓库**：kustomization 中 `images` 指向的 registry 可被集群拉取
- **ConfigMap/Secret**：CONFIG_VERSION、IMAGE_VERSION 等与 kustomize overlay 一致

### 4.3 Self-hosted Runner 标签（05b / 08）

`app-env-device-matrix-self-hosted.yml` 要求：

- **Android 矩阵**：Runner 同时具备标签 `self-hosted` 与 **`Linux`**（GitHub 为自托管机自动附加 OS 标签；Linux 主机注册后即可被选中）。
- **iOS 矩阵**：Runner 同时具备 `self-hosted` 与 **`macOS`**。

若仅有 **macOS** 自托管机，则无法满足「Android job 要求 `Linux`」的调度约束；应 **新增一台 Linux runner**，或由团队约定后 **统一改为自定义 label**（例如两 job 均跑在带 `android`/`ios` 标签的同一组机器上，并同步修改 `runs-on`）。

### 4.4 合并 main 后手动验证清单（建议每次发版前执行）

1. **03 Delivery Gate**：`dev1.0` 推送后确认对应当前 `HEAD` 的 run 成功。
2. **04 Pre-Release Gate**：在 `main` 上确认 `gate`、`l3`、`l4`、`assistant` 及 `release-evidence-summary` 全绿；若红，查看 summary job 日志中的分项提示与 `GAMMA_*` 配置。
3. **06 Deploy To Prod (Auto)**：确认上游 04 成功触发；`production` Environment 若启用审批，在 GitHub 上完成 Stage 2 审批。
4. **08 Deploy Gamma ECS**：使用 `workflow_dispatch` 试跑 pre 阶段；确认 `GAMMA_ECS_PASSWORD` 或 `GAMMA_ECS_SSH_KEY`、self-hosted 在线且矩阵 job 未被队列饿死。

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
- `deploy/shared/branch_strategy.md` — 分支策略（dev1.0 日常合入、main 定时 merge）
- `deploy/shared/deliver_to_production_runbook.md` — 端到端运行手册
- `.github/workflows/pre-release-gate.yml` — 当前 pre-release 流程
- `scripts/deploy_to_integration.sh` — 构建脚本（需扩展或新建 apply 脚本）
- `specs/feature-tree/runtime/deliver-deploy-prod-pipeline/design.md` — 设计
