# GitHub Actions CI/CD — Secrets 与 Workflow 说明

本文档说明所有 Workflow 的触发条件、职责及需配置的 GitHub Secrets，与根 `AGENTS.md` 的执行契约对应。

**当前部署目标**：CI/CD 的唯一生产执行面是 `prod-hosted` 的 SSH-hosted rootless
Podman；ACK 仅作为后续演进项。volcengine、huaweicloud 入口保留，暂不接入 CI。

---

## 一、Workflow 总览（与主线阶段对应）

| Workflow | 触发 | 职责 | 对应阶段 |
|----------|------|------|----------|
| **delivery-gate.yml** | `pull_request(main)`、手动 | PR 主门禁：拓扑校验、L1+L2 | G0~G3 |
| **service_pipeline.yml** | `push main`、手动 | main 后 Go 构建、rec-model 镜像、kustomize 校验 | G2 |
| **app_pipeline.yml** | 仅由 mainline `workflow_call` | 四环境 Android/iOS/macOS/Web、Prod Ops Portal 与 immutable App OCI evidence | G2 / 候选 |
| **pre-release-gate.yml** | `pull_request(main)`、手动 | deploy → L3 → L4 → gamma smoke | G3→G5b |
| **app-env-device-matrix-self-hosted.yml** | `pull_request(main)` / 被调用 / 手动 | self-hosted 动态设备矩阵唯一入口 | G5b |
| **deploy-prod-auto.yml** | `push main`、手动 | main 后自动推进 prod 主链，并在 `canary` 承接真实远端集成复验 | G5c |
| **domain-governance.yml** | 每周、手动 | DNS 唯一记录收敛、DNS-01 续期与加密证书交接 | 环境治理 |

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

### 可选（替代 DOCKER_TOKEN）

| Secret | 用途 |
|--------|------|
| DOCKER_USERNAME | 用户名/密码认证 |
| DOCKER_PASSWORD | 与 DOCKER_USERNAME 配合 |

### 说明

- 构建与测试阶段可不配置 Secrets；`DOCKER_TOKEN` 缺省时使用 `GITHUB_TOKEN`。

---

## 四、App Pipeline（app_pipeline.yml）

### `release-signing` Environment 必须配置

`release-signing` 只保护候选签名和构建材料，不承担 production rollout 审批；
Production approval 仍只存在于 Prod 事务 job。该 Environment 若未配置或误设人工审批，
App 候选构建会 fail closed，且会把人为等待错误引入 600 秒关键路径。

| Secret | 用途 |
|--------|------|
| **QWQ_ANDROID_RELEASE_KEYSTORE_B64** | Base64 编码的 Android release keystore |
| **QWQ_ANDROID_RELEASE_STORE_PASSWORD** | Android keystore 密码 |
| **QWQ_ANDROID_RELEASE_KEY_ALIAS** | Android 签名 key alias |
| **QWQ_ANDROID_RELEASE_KEY_PASSWORD** | Android 签名 key 密码 |
| **QWQ_ANDROID_EXPECTED_SIGNING_CERTIFICATE_SHA256** | 受保护环境登记的 Android 正式签名证书 SHA-256；必须与 APK 实际签名一致 |
| **QWQ_ANDROID_ALPHA_GOOGLE_SERVICES_JSON** | Alpha Android Remote composition 的 Firebase 配置原文 |
| **QWQ_ANDROID_BETA_GOOGLE_SERVICES_JSON** | Beta Android Remote composition 的 Firebase 配置原文 |
| **QWQ_ANDROID_GAMMA_GOOGLE_SERVICES_JSON** | Gamma Android Remote composition 的 Firebase 配置原文 |
| **QWQ_ANDROID_PROD_GOOGLE_SERVICES_JSON** | Prod Android Remote composition 的 Firebase 配置原文 |
| **QWQ_IOS_DISTRIBUTION_CERT_P12_B64** | Base64 编码的 iOS Distribution P12 |
| **QWQ_IOS_DISTRIBUTION_CERT_PASSWORD** | iOS Distribution P12 密码 |
| **QWQ_IOS_PROVISIONING_PROFILE_B64** | Base64 编码的正式 Provisioning Profile |
| **QWQ_IOS_EXPORT_OPTIONS_PLIST_B64** | Base64 编码的 ExportOptions.plist |

### 发布证明

- 本 workflow 不再接受 tag 或独立手动发布；只能绑定 mainline 传入的完整 Git SHA。
- Android、iOS、macOS、Web 四个平台矩阵并行展开 16 个环境 shard；Prod 同时生成
  Android official、Public Web 和 Ops Portal 真实 payload。任一环境/平台缺失即硬失败。
- 每个矩阵 shard 直接写入 run/attempt 唯一的 GHCR OCI transport tag；aggregate 先将 tag
  原子解析为 digest，再只按 exact `ghcr.io/...@sha256:...` 回读并拒绝文件冲突。Actions
  Artifact 不参与 job 间交换。aggregate 校验全部实际 payload 后发布唯一正式 App evidence OCI；
  后续 seal 和环境晋级只接受该 workflow 输出的 exact digest ref。
- `ReleaseEvidenceManifest.applicationPackages[*][*].sourceRef` 使用
  `oci://ghcr.io/...@sha256:...`，`packageDigest` 来自实际 payload 内容；OCI transport digest
  仅证明传输物，不替代 candidate digest。

---

## 五、Pre-release Gate（pre-release-gate.yml）

### 必须配置（端到端闭环时）

| Secret | 用途 |
|--------|------|
| **GAMMA_TEST_AUTH_TOKEN** | `api_integration` / `user_acceptance` 鉴权 Token |

### 说明

- `api_integration` / `user_acceptance` 验证统一跑 `gamma-local`，默认 URL 由 `quwoquan_ops/environments/gamma/runtime.yaml` 经 `stackctl` 解析。
- 如需手动覆盖 local-gamma 入口，可在命令行或 workflow input 传 `gamma_base_url`，而不是维护第二套 GitHub secret。
- `user_acceptance` Patrol 已统一迁到 **本机 macOS self-hosted runner**，通过 `flutter devices --machine` 动态发现当前可见的 Android/iOS 模拟器或真机，并逐台执行；总设备数至少为 1。
- `main` 的 pull request 合入规则中，`03` / `04` / `05` 需同时配置为 required checks。

---

## 六、App Env Device Matrix（app-env-device-matrix-self-hosted.yml）

### self-hosted（pull_request / workflow_call / 手动统一复用）

| Secret | 用途 |
|--------|------|
| ALPHA_TEST_AUTH_TOKEN | alpha-local Remote 鉴权覆盖（按 validation profile 配置） |
| BETA_TEST_AUTH_TOKEN | beta-local 鉴权覆盖（可选） |
| GAMMA_TEST_AUTH_TOKEN | gamma-local 鉴权覆盖（可选） |
| PROD_TEST_AUTH_TOKEN | prod-sim/prod 鉴权覆盖（可选） |
| PROD_ACCOUNT_CLOSURE_TEST_AUTH_TOKEN | `production` Environment 内一次性注销账号 access token（仅手动证据） |
| PROD_ACCOUNT_CLOSURE_TEST_REFRESH_TOKEN | 同一一次性账号 refresh token（仅手动证据） |
| PROD_ACCOUNT_CLOSURE_OWNER_ID | 同一一次性账号 owner id（敏感证据，不得写入日志） |
| PROD_ACCOUNT_CLOSURE_PERSONA_ID | 同一一次性账号 active persona id（敏感证据，不得写入日志） |

### Actions Variable

| Variable | 用途 |
|----------|------|
| VIDEO_PLAYBACK_CANARY_WORK_ID | `environment-smoke` 当前已发布视频对象；缺失时设备矩阵 fail-closed |
| **RELEASED_RELEASE_EVIDENCE_REF** | Nightly schedule 与 Provider producer 共用的唯一稳定发现指针；值必须是 status=`released` 的 exact `ghcr.io/.../release-artifact@sha256:...`。消费端会校验完整 manifest/文件闭包、BuildKit SBOM/provenance、GitHub OIDC issuer 与 `deploy-prod-auto.yml` signer identity |

### 说明

- `app-env-device-matrix-self-hosted.yml` 已成为唯一的 **05. App Env Device Matrix** 入口；同时支持 `pull_request(main)`、被其他 workflow 调用以及手动调试。
- Nightly schedule 只读取 `RELEASED_RELEASE_EVIDENCE_REF`；手动 full/release-candidate 与
  reusable caller 只接受一个 `release_evidence_ref`。`candidateId`、`artifactDigest`、
  source Git SHA/workflow run、pilot/rollback attestation、Alpha/Beta/Gamma lifecycle 与
  Green Matrix 均从该 manifest-bound closure 导出，仓库不再配置任何 `NIGHTLY_*`。
- `provider-release-evidence.yml` 与 schedule 使用同一个稳定指针（手动输入的 exact ref
  可显式覆盖），并从同一 released candidate 重跑 compiled required nonprod cell set
  与 Prod user_acceptance cell set。仓库不再配置
  `PROVIDER_{ALPHA,BETA,GAMMA,IOS,ANDROID}_*` 路径或设备变量。
- 更新稳定指针时必须一次性写入刚由受控 Prod workflow 发布并完成 OIDC 验证的 terminal
  digest ref；禁止写 tag、`latest`、candidate/preprod/deployable ref 或裸 manifest 路径。
- gamma 网关默认从 topology `gamma-local.publicBases.api` 解析，不再依赖 `GAMMA_BASE_URL` GitHub secret。
- `05` 已统一固定到 **本机 macOS self-hosted runner**；不再依赖自定义 runner label，也不再依赖固定 `ANDROID_DEVICE_ID` / `IOS_DEVICE_ID`。
- `alpha` 设备测试与其他环境使用同一 production Remote composition；第一方业务对象来自已激活 canonical release，所需鉴权按环境 validation profile 配置，禁止 runner/UAT fixture override。
- `beta` 在 runner 内启动本地 beta assistant-service + gateway；设备列表通过 `flutter devices --machine` 动态发现，当前可见的每台 Android/iOS 模拟器或真机都会执行。
- 四环境 token 严格按环境变量解析；禁止 alpha/beta/prod 回退复用 `GAMMA_TEST_AUTH_TOKEN`。
- beta CI 默认使用 deterministic provider；真实模型链路仍以人工/专门 beta 验证为准。
- Gamma 账号注销已进入 `nightly_full` / `release_candidate` 的
  `account-closure` 设备矩阵，并按设备生成独立 install identity。
- Prod 账号注销只允许手动 `workflow_dispatch`：传
  `env_json=["prod"]`、`matrix_kind=account-closure` 且显式确认
  `account_closure_disposable_ack=true`，并以
  `account_closure_prod_platform` + `account_closure_prod_device_id` 唯一选择一台设备；
  同一组凭据禁止并发或跨设备复用。四项 `PROD_ACCOUNT_CLOSURE_*`
  必须配置在受审批的 `production` GitHub Environment，且每次运行前替换为新建、允许永久注销的一次性账号；不得复用日常验收账号。

### self-hosted runner 前提

| 条目 | 用途 |
|------|------|
| **`self-hosted` + `macOS` runner** | 所有设备类 job 统一调度到当前开发 Mac |
| **可见移动设备 ≥ 1** | `flutter devices --machine` 至少能看到一台 Android/iOS 模拟器或真机，否则矩阵直接 `gate_block` |

---

## 七、远端 Gamma（已退役）

远端 ECS gamma onebox 部署已退役，所有 `GAMMA_ECS_*` secret/var（`GAMMA_ECS_SSH_KEY`、`GAMMA_ECS_PASSWORD`、`GAMMA_ECS_HOST`、`GAMMA_ECS_REMOTE_DIR`、`GAMMA_ECS_CONTAINER_REGISTRY_MIRROR`、`GAMMA_ECS_*_TIMEOUT_SECONDS` 等）均不再使用。

- `gamma` 仅本地（local-gamma mirror），本地 left-shift 验证不需要任何远端 secret。
- 真实远端发布、就地升级与集成 / curated 媒体路由复验统一由 prod `canary` rollout stage 承接（见第八节 `deploy-prod-auto.yml`）。
- prod 远端访问统一走**按平面 SSH 凭据**（见第八节），不得复用任何 `GAMMA_ECS_*` 命名，亦不再使用单一全权 `PROD_KUBECONFIG`。

---

## 八、Prod Hosted Deploy（deploy-prod-auto.yml）

> 远端唯一托管目标为 `prod-hosted`（backend=ssh-hosted，与原 gamma 同台 ECS，rootless podman compose）。
> 已**退役** `PROD_KUBECONFIG` 单一全权凭据，改为按 `edge / media / service / data` 四平面去 root 隔离的 SSH 凭据。
> 访问隔离单一真相源：`quwoquan_ops/environments/prod/access-isolation.yaml`。

### 必须配置

| Secret | 用途 |
|--------|------|
| **PROD_EDGE_SSH_KEY** | `edge` 平面账号 `prod-edge-svc` 的 SSH 私钥（realtime-gateway / rtc-service） |
| **PROD_MEDIA_SSH_KEY** | `media` 平面账号 `prod-media-svc` 的 SSH 私钥（livekit-sfu / coturn） |
| **PROD_SERVICE_SSH_KEY** | `service` 平面账号 `prod-service-svc` 的 SSH 私钥（各第一方服务自治 workload） |
| **AI_CI_SHADOW_TOKEN** | 仅可调用脱敏 CI 建议端点的短期只读 token；不得拥有仓库、门禁、部署或云资源权限 |
| **PROD_PROMETHEUS_URL**（Environment variable） | 生产 Prometheus API base URL，供 `stackctl deploy` 自动回读 error rate/P95/Redis error rate |
| **PROD_ALERTMANAGER_URL**（Environment variable） | 生产 Alertmanager API base URL，供 full rollout 后 canonical soak 证明无 active firing alerts |
| **PROD_{EDGE,SERVICE}_SSH_KEY_REFERENCE**（Environment variable） | 凭据管理系统中的不可变安全引用；不得填写私钥、token 或 runner 本地路径 |
| **PROD_{EDGE,SERVICE}_SSH_KEY_PUBLIC_DIGEST**（Environment variable） | 对规范化 SSH 公钥 bytes 的 `sha256:` 摘要，必须与运行时私钥导出的公钥一致 |
| **PROD_{EDGE,SERVICE}_SSH_KEY_ISSUER**（Environment variable） | 凭据签发方标识 |
| **PROD_{EDGE,SERVICE}_SSH_KEY_EXPIRES_AT**（Environment variable） | 带时区的凭据到期时间；过期或缺失会阻断 hosted soak receipt |
| **PROD_SERVICE_NETWORK**（prod-hosted 主机变量） | Prometheus/Alertmanager/OTel Collector 加入的 service plane 共享 rootless network 名称 |
| **OTEL_EXPORTER_OTLP_ENDPOINT**（prod-hosted 主机变量，可选） | 服务 trace 的 OTLP/HTTP 接收端（`host:port`）；未设置时使用共享网络内 `otel-collector:4318` |
| **PROD_OPS_OIDC_ISSUER**（Environment variable） | 运维运营 Portal 的生产 OIDC issuer（`build_portal_release.py` 构建期注入） |
| **PROD_OPS_OIDC_CLIENT_ID**（Environment variable） | Portal 生产 OIDC 公共 client id（SPA，非机密） |
| **PROD_OPS_OIDC_AUDIENCE**（Environment variable） | Portal 与 `product-ops-service` / `platform-ops-service` 共用的生产控制面 API audience |
| **PROD_OPS_OIDC_SCOPE**（Environment variable） | IdP 为 Portal client 登记的最小 operator scope 集；必须包含 `openid` 与菜单所需权限 |
| **OPS_OIDC_ISSUER / OPS_OIDC_AUDIENCE / OPS_OIDC_JWKS_URL**（prod-hosted 主机变量） | 两个 Ops 服务的服务端 OIDC 验签配置；任一缺失时 production composition 拒绝启动 |
| **ALERT_INGEST_TOKEN**（prod-hosted 主机变量） | Alertmanager → platform-ops-service 告警回流 ingest 的机器 token；与观测栈 `ALERT_INGEST_TOKEN_SECRET_FILE` 内容一致 |
| **RUNTIME_LOG_INGEST_TOKEN**（prod-hosted 主机变量） | 云侧服务日志上云内部通道（各服务 → product-ops `/ops/internal/runtime-logs:ingest`）的机器 token；服务端 fail-closed |
| **PROD_RELEASE_STATE_DIR**（Environment variable） | Prod runner 的可删除 hosted-ledger 回读缓存目录；不作为发布真相源 |
| **PROD_BACKUP_RECOVERY_RECEIPT**（Environment variable） | 当前有效的 hosted 备份与隔离恢复回执路径；校验失败或过期时阻断发布 |
| **PROD_ROLLBACK_DRILL_RECEIPT_ID**（Environment variable） | 已成功真实回滚的 hosted ledger receipt SHA-256 id；发布前必须从 service plane 按 id 回读并验真 |
| **PROD_PROVIDER_EVIDENCE_REF**（Repository variable） | 受控 Provider conformance 原始证据的 exact GHCR OCI digest ref；Delivery runner 只按 digest 回读 |
| **PROD_PROVIDER_EVIDENCE_DIGEST**（Repository variable） | 上述 Provider evidence OCI 的 `sha256:...` transport digest，必须与 ref 一致 |
| **RELEASE_USER_ACCEPTANCE_EVIDENCE_REF**（Repository variable） | 与待发布 Git tree、ContractGraph 和候选制品内容摘要一致的真实 Remote `user_acceptance` 证据 exact GHCR OCI digest ref；禁止用 contract smoke 代替 |
| **RELEASE_USER_ACCEPTANCE_EVIDENCE_DIGEST**（Repository variable） | 上述真实 Remote `user_acceptance` OCI 的 `sha256:...` transport digest，必须与 ref 一致 |

### 说明

- 每个 GitHub Secret 保存 **OpenSSH/PEM 私钥原文**（含 `BEGIN ... PRIVATE KEY`），不是文件路径。workflow 必须在 `$RUNNER_TEMP` 以 `0600` 权限一次性物化，并仅通过 `<SSH_KEY_SECRET>_FILE` 交给发布 CLI；CLI 不把原文或本地缓存当作 hosted authority。
- `PROD_SSH_HOST` 属于受限管理面，必须单独注入；禁止从面向 App 的
  `prod-hosted.publicBases.api` 推导。
- `AI_CI_SHADOW_ENDPOINT` 是 repository variable，必须是无凭据的 HTTPS URL；
  对应 shadow job 不在候选制品、四环境或 Prod 晋级的依赖链中，输出仅为
  canonical `AiCiAdvisory`，失败不得修改任何确定性门禁结果。
- `deploy-prod-auto.yml` 在真实发布（`dry_run != true`）前会调用 `quwoquan_ops/cli/prod/validate_prod_plane_credentials.py` 按 rollout stage 硬校验对应平面凭据；缺失/非法即硬失败。生产灰度只是 `prod` 的 rollout stage，不存在第二个 Prod workflow 或环境。
- `deploy-prod-auto.yml` 的 dry-run 同样读取托管 ledger、真实回滚演练和备份恢复证据；三者缺一时停在 `candidate-ready`，不得生成 `deployable` 或伪造 Prod 回执。
- mainline `CiTimingSummary` 由最终 summary job 以 exact GHCR OCI digest 发布，并使用 `PROD_SERVICE_SSH_KEY` 写入 `/home/prod-service-svc/stack/ci-timing-ledger` 的独立 append-only authority；该 authority 不复用 Prod rollout CAS。
- hosted timing authority 必须由运维预先执行 `hosted_ci_timing_ledger.py --action initialize` 建立 marker。workflow 只有 bind/query 路径，缺 marker、SSH、exact OCI digest 或读后不一致均 `GATE_BLOCK`；三天 Actions Artifact 只是诊断副本。
- `quwoquan_ops/cli/prod/deploy_to_prod.sh` 按平面账号 `prod-<plane>-svc` 自登录，`podman compose` 拉起本平面 governedWorkloads + rollout 等待 + 失败回滚；**不再允许**凭据缺失时以 warning 形式跳过并返回成功。
- `PROD_KUBECONFIG` 已退役：一旦检测到该变量被注入，`deploy_to_prod.sh` 与凭据校验脚本都会直接硬失败，禁止 kube 路径复活。
- `PROD_OPS_SSH_KEY`（relay）与 `PROD_DATA_SSH_KEY`（readonly audit）只在本地 bootstrap / 审计场景下按需生成，不属于当前 GitHub Actions 发布最小 secret 集。
- 账号一次性创建见 `quwoquan_ops/cli/prod/bootstrap_prod_plane_accounts.sh`（去 root、rootless podman、独立 home/compose 根/credentials）。
- `canary` 先取 candidate 服务池单实例验证（承接原远端 gamma 验证职责），通过后依次推进 `5/20/50/100`；candidate 与 stable 服务池共享同一物理 ECS 为成本驱动保留项。
- 非 dry-run 发布禁止使用 workflow 输入中的 SLO 数字；`stackctl deploy` 必须通过
  `PROD_PROMETHEUS_URL` 查询生产窗口，并由
  `quwoquan_ops/policies/config-release/slo_thresholds.yaml` 唯一决定
  continue/pause/rollback。
- 观测栈启动还需要 rootless 主机 Secret 文件
  `ALERTMANAGER_WEBHOOK_SECRET_FILE`；通知 URL 不进入 GitHub 仓库或 workflow 日志。

---

## 九、项目结构与路径

```
├── quwoquan_service/     # Go monorepo + recommendation-service (Python)
├── quwoquan_app/         # Flutter 应用
├── quwoquan_service/services/*/environments/{alpha,beta,gamma,prod}/deploy/
├── quwoquan_ops/environments/{alpha,beta,gamma,prod}/
├── quwoquan_ops/external/{coturn,livekit}/
└── .github/workflows/
    ├── delivery-gate.yml
    ├── service_pipeline.yml
    ├── app_pipeline.yml
    ├── pre-release-gate.yml
    ├── domain-governance.yml
    ├── deploy-prod-auto.yml
    └── app-env-device-matrix-self-hosted.yml
```

---

## 十、Domain Governance

在 GitHub `domain-governance` Environment 配置：

| Secret | 用途 |
|--------|------|
| `QWQ_DNS_PROVISIONING_API_TOKEN` | Cloudflare DNS provisioning token，仅供 canonical A/AAAA/CAA/MX/TXT/CNAME apply |
| `QWQ_ACME_DNS_API_TOKEN` | Cloudflare DNS-01 challenge-only token，仅授权非生产 `_acme-challenge` authority，禁止生产区变更 |
| `QWQ_DNS_ZONE_ID` | `quwoquan.com` zone id |
| `QWQ_ACME_ACCOUNT_EMAIL` | Let's Encrypt ACME account |
| `QWQ_TLS_AGE_RECIPIENT` | 证书部署方持有私钥的 age 公钥；CI 只上传加密后的证书包 |

Workflow 不上传明文私钥；证书包以 age 加密、保留 7 天。DNS apply 与 live DNS
证据不含 token，保留 30 天。生产证书仍由 `public-ca-prod` 外部发布面管理。

---

## 十一、配置步骤

1. 进入仓库 **Settings → Secrets and variables → Actions**。
2. 点击 **New repository secret**。
3. 按上述各 Workflow 表格添加所需 Secrets。
4. 保存后，对应 push/PR/tag 或手动触发时将使用新 Secrets。
5. 若已在本机生成 prod 平面私钥，可直接自动同步并清理退役项：`bash quwoquan_ops/cli/prod/setup_prod_plane_ssh_access.sh --mode all --include-relay --include-readonly --github-sync --github-prune-obsolete-secrets`

**参考**：`quwoquan_ops/environments/prod/access-isolation.yaml`、`quwoquan_ops/environments/prod/rollout/stages.yaml`。
