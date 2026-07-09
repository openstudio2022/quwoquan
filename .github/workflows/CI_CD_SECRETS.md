# GitHub Actions CI/CD — Secrets 与 Workflow 说明

本文档说明所有 Workflow 的触发条件、职责及需配置的 GitHub Secrets，与 `specs/00_MASTER_DEVELOPMENT_FLOW.md` 阶段对应。

**当前部署目标**：CI/CD 仅考虑**阿里云 ACK** 部署（integration/prod）。volcengine、huaweicloud 入口保留，暂不接入 CI。

---

## 一、Workflow 总览（与主线阶段对应）

| Workflow | 触发 | 职责 | 对应阶段 |
|----------|------|------|----------|
| **delivery-gate.yml** | `pull_request(main)`、手动 | PR 主门禁：拓扑校验、L1+L2 | G0~G3 |
| **service_pipeline.yml** | `push main`、手动 | main 后 Go 构建、rec-model 镜像、kustomize 校验 | G2 |
| **app_pipeline.yml** | `v*` tag、手动 | macOS 构建（主干门禁已由 03/04/05 负责） | G2 / 发布 |
| **pre-release-gate.yml** | `pull_request(main)`、手动 | deploy → L3 → L4 → gamma smoke | G3→G5b |
| **app-env-device-matrix-self-hosted.yml** | `pull_request(main)` / 被调用 / 手动 | self-hosted 动态设备矩阵唯一入口 | G5b |
| **deploy-prod.yml** | 手动 | 半自动 prod 发布 | G5c |
| **deploy-prod-auto.yml** | `push main`、手动 | main 后自动推进 prod 主链，并在 `gray-initial` 承接真实远端集成复验 | G5c |

---

## 二、Delivery Gate（delivery-gate.yml）

**Secrets**：无。仅需仓库代码与脚本。

---

## 三、Service Pipeline（service_pipeline.yml）

### 必须配置（仅部署时）

| Secret | 用途 | 示例值 |
|--------|------|--------|
| **DOCKER_REGISTRY** | Docker 镜像仓库地址 | `ghcr.io` 或 `registry.example.com` |
| **DOCKER_TOKEN** | 镜像仓库推送凭证（或使用 GITHUB_TOKEN） | `ghp_xxx` |
| **KUBECONFIG** | 目标 K8s 集群 kubeconfig，**base64 编码** | `base64 -w0 ~/.kube/config` 输出 |

### 可选（替代 DOCKER_TOKEN）

| Secret | 用途 |
|--------|------|
| DOCKER_USERNAME | 用户名/密码认证 |
| DOCKER_PASSWORD | 与 DOCKER_USERNAME 配合 |

### 说明

- 构建与测试阶段可不配置 Secrets；`DOCKER_TOKEN` 缺省时使用 `GITHUB_TOKEN`。

---

## 四、App Pipeline（app_pipeline.yml）

### 必须配置

无。常规单元测试、v* tag 下 macOS 构建均无需额外 Secrets。

### 可选

| Secret | 用途 |
|--------|------|
| CODESIGN_IDENTITY | macOS 签名身份（codesign） |
| MATCH_PASSWORD | fastlane match 证书密码 |

---

## 五、Pre-release Gate（pre-release-gate.yml）

### 必须配置（端到端闭环时）

| Secret | 用途 |
|--------|------|
| **GAMMA_TEST_AUTH_TOKEN** | `api_integration` / `user_acceptance` 鉴权 Token |

### 说明

- 远端 gamma 已退役；`api_integration` / `user_acceptance` 验证统一跑 `gamma-local`，默认 URL 从 `quwoquan_ops/environments/environment_topology_manifest.yaml` 的 `gamma-local.publicBases.*` 解析。
- 如需手动覆盖 local-gamma 入口，可在命令行或 workflow input 传 `gamma_base_url`，而不是维护第二套 GitHub secret。
- `user_acceptance` Patrol 已统一迁到 **本机 macOS self-hosted runner**，通过 `flutter devices --machine` 动态发现当前可见的 Android/iOS 模拟器或真机，并逐台执行；总设备数至少为 1。
- `main` 的 pull request 合入规则中，`03` / `04` / `05` 需同时配置为 required checks。

---

## 六、App Env Device Matrix（app-env-device-matrix-self-hosted.yml）

### self-hosted（pull_request / workflow_call / 手动统一复用）

| Secret | 用途 |
|--------|------|
| **GAMMA_TEST_AUTH_TOKEN** | beta/gamma 远端链路鉴权 |

### 说明

- `app-env-device-matrix-self-hosted.yml` 已成为唯一的 **05. App Env Device Matrix** 入口；同时支持 `pull_request(main)`、被其他 workflow 调用以及手动调试。
- gamma 网关默认从 topology `gamma-local.publicBases.api` 解析，不再依赖 `GAMMA_BASE_URL` GitHub secret。
- `05` 已统一固定到 **本机 macOS self-hosted runner**；不再依赖自定义 runner label，也不再依赖固定 `ANDROID_DEVICE_ID` / `IOS_DEVICE_ID`。
- `alpha` 使用 `APP_DATA_SOURCE=mock`，不需要云侧 Secret。
- `beta` 在 runner 内启动本地 beta assistant-service + gateway；设备列表通过 `flutter devices --machine` 动态发现，当前可见的每台 Android/iOS 模拟器或真机都会执行。
- beta CI 默认使用 deterministic provider；真实模型链路仍以人工/专门 beta 验证为准。

### self-hosted runner 前提

| 条目 | 用途 |
|------|------|
| **`self-hosted` + `macOS` runner** | 所有设备类 job 统一调度到当前开发 Mac |
| **可见移动设备 ≥ 1** | `flutter devices --machine` 至少能看到一台 Android/iOS 模拟器或真机，否则矩阵直接 `gate_block` |

---

## 七、远端 Gamma（已退役）

远端 ECS gamma onebox 部署已退役，所有 `GAMMA_ECS_*` secret/var（`GAMMA_ECS_SSH_KEY`、`GAMMA_ECS_PASSWORD`、`GAMMA_ECS_HOST`、`GAMMA_ECS_REMOTE_DIR`、`GAMMA_ECS_CONTAINER_REGISTRY_MIRROR`、`GAMMA_ECS_*_TIMEOUT_SECONDS` 等）均不再使用。

- `gamma` 仅本地（local-gamma mirror），本地 left-shift 验证不需要任何远端 secret。
- 真实远端发布、就地升级与集成 / curated 媒体路由复验统一由 prod `gray-initial` rollout stage 承接（见第八节 `deploy-prod-auto.yml`）。
- prod 远端访问统一走**按平面 SSH 凭据**（见第八节），不得复用任何 `GAMMA_ECS_*` 命名，亦不再使用单一全权 `PROD_KUBECONFIG`。

---

## 八、Prod Hosted Deploy（deploy-prod-gray.yml / deploy-prod-auto.yml）

> 远端唯一托管目标为 `prod-hosted`（backend=ssh-hosted，与原 gamma 同台 ECS，rootless podman compose）。
> 已**退役** `PROD_KUBECONFIG` 单一全权凭据，改为按 `edge / media / service / data` 四平面去 root 隔离的 SSH 凭据。
> 访问隔离单一真相源：`quwoquan_ops/environments/prod_plane_access_isolation.yaml`。

### 必须配置

| Secret | 用途 |
|--------|------|
| **PROD_EDGE_SSH_KEY** | `edge` 平面账号 `prod-edge-svc` 的 SSH 私钥（realtime-gateway / rtc-service） |
| **PROD_MEDIA_SSH_KEY** | `media` 平面账号 `prod-media-svc` 的 SSH 私钥（livekit-sfu / coturn） |
| **PROD_SERVICE_SSH_KEY** | `service` 平面账号 `prod-service-svc` 的 SSH 私钥（seed-box 及同集群独立 workload） |

### 说明

- 每个平面 SSH 私钥都是 **OpenSSH/PEM 私钥原文**（含 `BEGIN ... PRIVATE KEY`），不是文件路径。
- prod SSH host 默认直接从 `environment_topology_manifest.yaml` 的 `prod-hosted.publicBases.api` 解析，不再需要单独维护 `PROD_SSH_HOST` secret。
- `deploy-prod-gray.yml` 与 `deploy-prod-auto.yml` 在真实发布（`dry_run != true`）前会调用 `quwoquan_ops/cli/prod/validate_prod_plane_credentials.py` 按 rollout stage 硬校验对应平面凭据；缺失/非法即硬失败。
- `quwoquan_ops/cli/prod/deploy_to_prod.sh` 按平面账号 `prod-<plane>-svc` 自登录，`podman compose` 拉起本平面 governedWorkloads + rollout 等待 + 失败回滚；**不再允许**凭据缺失时以 warning 形式跳过并返回成功。
- `PROD_KUBECONFIG` 已退役：一旦检测到该变量被注入，`deploy_to_prod.sh` 与凭据校验脚本都会直接硬失败，禁止 kube 路径复活。
- `PROD_OPS_SSH_KEY`（relay）与 `PROD_DATA_SSH_KEY`（readonly audit）只在本地 bootstrap / 审计场景下按需生成，不属于当前 GitHub Actions 发布最小 secret 集。
- 账号一次性创建见 `quwoquan_ops/cli/prod/bootstrap_prod_plane_accounts.sh`（去 root、rootless podman、独立 home/compose 根/credentials）。
- 灰度（`gray-initial`）取同集群一个实例验证（承接原远端 gamma 验证职责），通过后放量 `full`；二者共享同一物理 ECS 为成本驱动保留项。

---

## 九、项目结构与路径

```
├── quwoquan_service/     # Go monorepo + rec-model-service (Python)
├── quwoquan_app/         # Flutter 应用
├── quwoquan_service/services/seed-box/deploy/kustomize/overlays/
└── .github/workflows/
    ├── delivery-gate.yml
    ├── service_pipeline.yml
    ├── app_pipeline.yml
    ├── pre-release-gate.yml
    ├── deploy-prod-auto.yml
    └── app-env-device-matrix-self-hosted.yml
```

---

## 十、配置步骤

1. 进入仓库 **Settings → Secrets and variables → Actions**。
2. 点击 **New repository secret**。
3. 按上述各 Workflow 表格添加所需 Secrets。
4. 保存后，对应 push/PR/tag 或手动触发时将使用新 Secrets。
5. 若已在本机生成 prod 平面私钥，可直接自动同步并清理退役项：`bash quwoquan_ops/cli/prod/setup_prod_plane_ssh_access.sh --mode all --include-relay --include-readonly --github-sync --github-prune-obsolete-secrets`

**参考**：`quwoquan_ops/environments/ci_cd_end_to_end_design.md`、`quwoquan_ops/environments/deliver_to_production_runbook.md`。
