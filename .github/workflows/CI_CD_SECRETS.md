# GitHub Actions CI/CD — Secrets 与 Workflow 说明

本文档说明所有 Workflow 的触发条件、职责及需配置的 GitHub Secrets，与 `specs/00_MASTER_DEVELOPMENT_FLOW.md` 阶段对应。

**当前部署目标**：CI/CD 仅考虑**阿里云 ACK** 部署（integration/prod）。volcengine、huaweicloud 入口保留，暂不接入 CI。

---

## 一、Workflow 总览（与主线阶段对应）

| Workflow | 触发 | 职责 | 对应阶段 |
|----------|------|------|----------|
| **delivery-gate.yml** | PR / push main, dev1.0 | 拓扑校验、L1+L2 质量门（PR/入库阶段） | G0~G3 |
| **service_pipeline.yml** | quwoquan_service/**、deploy/** | Go 构建、rec-model 镜像、kustomize 校验 | G2 |
| **app_pipeline.yml** | quwoquan_app/**；v* tag → macOS 构建 | Flutter analyze、macOS 构建（L1 由 delivery-gate 负责） | G2 / 发布 |
| **pre-release-gate.yml** | v*-rc* tag、手动 | L1+L2 → deploy → L3 → L4（L3 统一整合） | G3→G5b |
| **deploy-gamma-ecs.yml** | 手动、push main | hosted gate/打包 → self-hosted alpha/beta 预检 → ECS pre → self-hosted 矩阵 → prod 就地升级 | G5a→G5b |
| **app-env-device-matrix-self-hosted.yml** | 被调用 / 手动 | alpha/beta/gamma self-hosted 端侧矩阵 | G5b |
| **ecs-onebox-rollback.yml** | 手动 | ECS onebox 备份回滚 | 运维 |

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
| **GAMMA_BASE_URL** | gamma API 地址（L3/L4 使用） |
| **GAMMA_PRODUCT_OPS_BASE_URL** | gamma Product Ops API 地址（L3 使用） |
| **GAMMA_TEST_AUTH_TOKEN** | L3/L4 鉴权 Token |
| **GAMMA_KUBECONFIG** | gamma 集群 kubeconfig，**base64 编码** |

### 说明

- `GAMMA_KUBECONFIG` 未配置时，deploy-integration 仅 skip，不 fail。
- L3/L4 依赖 deploy-integration 完成，需 gamma 已部署且 `GAMMA_BASE_URL` 可访问。
- L4 Android 使用 GitHub hosted `ubuntu-latest` + Android Emulator；L4 iOS 使用 GitHub hosted `macos-latest` + iOS Simulator，不再依赖 Firebase Test Lab / GCP 凭证。
- 若注册 self-hosted runner，可将仓库变量 **`QWQ_SELF_HOSTED_PRE_RELEASE_MATRIX`** 设为 **`true`**，在 L3 通过后额外执行 **alpha/beta/gamma** self-hosted 矩阵（`app-env-device-matrix-self-hosted.yml`）。

---

## 六、App Env Device Matrix（app-env-device-matrix.yml / app-env-device-matrix-self-hosted.yml）

### self-hosted（dev1.0/main push 与 05b 统一复用）

| Secret | 用途 |
|--------|------|
| **GAMMA_BASE_URL** | gamma 场景或手动覆盖时使用；`dev1.0/main` push 的 `05` 当前固定跑 `alpha/beta`，通常不需要 |
| **GAMMA_TEST_AUTH_TOKEN** | beta/gamma 远端链路鉴权 |

### 说明

- `app-env-device-matrix.yml` 已改为 **wrapper**：`dev1.0/main` 的每次 push 统一调用 **05b `app-env-device-matrix-self-hosted.yml`**，不再使用 GitHub hosted 模拟器。
- self-hosted runner 需带自定义标签 **`app-device-android`** / **`app-device-ios`**；单台 macOS 本机若同时具备 Android Emulator 与 iOS Simulator，可同时挂这两个标签。
- `alpha` 使用 `APP_DATA_SOURCE=mock`，不需要云侧 Secret。
- `beta` 在 runner 内启动本地 beta assistant-service + gateway；设备通过仓库变量 `ANDROID_DEVICE_ID` / `IOS_DEVICE_ID` 指向本机模拟器或真机。
- beta CI 默认使用 deterministic provider；真实模型链路仍以人工/专门 beta 验证为准。

### self-hosted 可选 Variables

| Variable | 用途 |
|----------|------|
| **ANDROID_DEVICE_ID** | 物理机/adb 设备 id（默认 `emulator-5554`） |
| **IOS_DEVICE_ID** | 真机或模拟器 UDID；未设置时在 macOS runner 上自动 boot 模拟器 |

---

## 七、Gamma ECS Deploy（deploy-gamma-ecs.yml）

### 认证（二选一）

| Secret | 用途 |
|--------|------|
| **GAMMA_ECS_SSH_KEY** | ECS SSH 私钥全文（推荐） |
| **GAMMA_ECS_PASSWORD** | ECS SSH 密码（与 `sshpass`；可与密钥互斥） |

### 必须配置

| Secret / Variable | 用途 |
|--------|------|
| **GAMMA_TEST_AUTH_TOKEN** | gamma T3 / 远端脚本 `run_local_gamma_t3` 验证 Token |

### 可选配置

| Secret / Variable | 用途 | 默认值 |
|--------|------|------|
| GAMMA_ECS_HOST | ECS 公网地址 | `118.31.239.122` |
| GAMMA_ECS_USER | SSH 用户名 | `root` |
| GAMMA_ECS_PORT | SSH 端口 | `22` |
| GAMMA_ECS_REMOTE_DIR | ECS 部署目录 | `/opt/quwoquan/gamma` |
| GAMMA_BASE_URL | gamma 内容 API 公网基址 | `http://<GAMMA_ECS_HOST>:18080` |
| GAMMA_PRODUCT_OPS_BASE_URL | gamma Product Ops API 公网基址 | `http://<GAMMA_ECS_HOST>:18086` |
| **GAMMA_ECS_CONTAINER_REGISTRY_MIRROR** | ECS 侧 Podman 的 `docker.io` 镜像加速主机名（大路访问 Docker Hub 慢/超时时强烈推荐） | 留空=直连 Docker Hub |
| GAMMA_ECS_IMAGE_PULL_TIMEOUT_SECONDS | 远端预拉镜像单镜像超时（秒） | 脚本默认 `600` |
| GAMMA_ECS_COMPOSE_TIMEOUT_SECONDS | 远端 compose build+up 外层超时（秒） | 脚本默认 `5400` |

### 说明

- **hosted**：`make gate` → **打包 tarball artifact**。
- **ECS pre**：`scripts/deploy_gamma_ecs.sh`（`GAMMA_ECS_STAGE=pre`，`GAMMA_DEPLOY_IMAGE_VERSION=<sha>`），上传 bundle；远端写 `.gamma_deploy_state.json`，并在 `../gamma-backups/` 保留备份 tarball。
- **T3**：`make test-api-contract`（gamma）。
- **self-hosted**：调用 `app-env-device-matrix-self-hosted.yml`（alpha/beta/gamma）；runner 需带 `app-device-android` / `app-device-ios` 标签。
- **ECS prod**：同一 ECS **就地升级**（`GAMMA_ECS_STAGE=prod`，`GAMMA_ECS_SKIP_UPLOAD=1`，`GAMMA_DEPLOY_IMAGE_VERSION=<sha>-prod`），然后再跑 T3 与 **gamma-only** self-hosted 烟测。
- ECS 上使用 Podman 兼容层拉取镜像时，`GAMMA_ECS_CONTAINER_REGISTRY_MIRROR` 未配置则可能长时间直连 `docker.io`，在大陆网络下易超时；建议配置可用的镜像加速或使用自有镜像仓库前置基础镜像。
- **Deploy ECS — pre/prod** 单 Job 超时为 **120** 分钟（含首次镜像 build）；请勿在流水线中途手动 Cancel，否则会向 SSH 子进程发送 SIGTERM（常见于 exit 143）。
- **回滚**：手动触发 **08b `ecs-onebox-rollback.yml`** 或本地执行 `scripts/rollback_gamma_ecs.sh`（恢复最近一次 `backup-*.tgz`）。
- 结构化部署报告：`artifacts/ecs-onebox/deploy-report.json`（成功/失败阶段会上传为 artifact）。
- ECS 安全组需放行 SSH、`18080`、`18086`（或同步修改 health 探测 URL）。

---

## 八、项目结构与路径

```
├── quwoquan_service/     # Go monorepo + rec-model-service (Python)
├── quwoquan_app/         # Flutter 应用
├── deploy/service/seed-box/kustomize/overlays/
└── .github/workflows/
    ├── delivery-gate.yml
    ├── service_pipeline.yml
    ├── app_pipeline.yml
    ├── pre-release-gate.yml
    ├── deploy-gamma-ecs.yml
    ├── app-env-device-matrix-self-hosted.yml
    └── ecs-onebox-rollback.yml
```

---

## 九、配置步骤

1. 进入仓库 **Settings → Secrets and variables → Actions**。
2. 点击 **New repository secret**。
3. 按上述各 Workflow 表格添加所需 Secrets。
4. 保存后，对应 push/PR/tag 或手动触发时将使用新 Secrets。

**参考**：`deploy/shared/ci_cd_end_to_end_design.md`、`deploy/shared/deliver_to_production_runbook.md`。
