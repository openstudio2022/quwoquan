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

---

## 六、App Env Device Matrix（app-env-device-matrix.yml）

### 必须配置（gamma 覆盖时）

| Secret | 用途 |
|--------|------|
| **GAMMA_BASE_URL** | gamma 端侧远端网关地址 |

### 说明

- 覆盖矩阵为 `alpha/beta/gamma × Android/iOS`。
- `alpha` 使用 `APP_DATA_SOURCE=mock`，不需要云侧 Secret。
- `beta` 在 GitHub hosted runner 内启动本地 beta assistant-service + gateway；Android 通过 `10.0.2.2` 访问 runner，iOS 通过 `127.0.0.1` 访问 runner。
- `gamma` 连接公网可达的 `GAMMA_BASE_URL`，不依赖本地 DNS/TLS。
- beta CI 默认使用 deterministic provider，避免端侧环境 smoke 被外部模型供应商可用性阻塞；真实模型链路仍以人工/专门 beta 验证为准。

---

## 七、项目结构与路径

```
├── quwoquan_service/     # Go monorepo + rec-model-service (Python)
├── quwoquan_app/         # Flutter 应用
├── deploy/service/seed-box/kustomize/overlays/
└── .github/workflows/
    ├── delivery-gate.yml
    ├── service_pipeline.yml
    ├── app_pipeline.yml
    └── pre-release-gate.yml
```

---

## 七、配置步骤

1. 进入仓库 **Settings → Secrets and variables → Actions**。
2. 点击 **New repository secret**。
3. 按上述各 Workflow 表格添加所需 Secrets。
4. 保存后，对应 push/PR/tag 或手动触发时将使用新 Secrets。

**参考**：`deploy/shared/ci_cd_end_to_end_design.md`、`deploy/shared/deliver_to_production_runbook.md`。
