# GitHub Actions CI/CD — Secrets 与 Workflow 说明

本文档说明所有 Workflow 的触发条件、职责及需配置的 GitHub Secrets，与根 `AGENTS.md` 的执行契约对应。

**当前部署目标**：CI/CD 的唯一生产执行面是 `prod-hosted` 的 SSH-hosted rootless
Podman；ACK 仅作为后续演进项。volcengine、huaweicloud 入口保留，暂不接入 CI。

---

## 一、Workflow 总览（与主线阶段对应）

| Workflow | 触发 | 职责 | 对应阶段 |
|----------|------|------|----------|
| **delivery-gate.yml** | `push dev1.0`、`pull_request(dev1.0 -> main)`、手动 | 集成与 promotion 主门禁：拓扑校验、L1+L2 | G0~G3 |
| **service_pipeline.yml** | `push main`、手动 | main 后 Go 构建、rec-model 镜像、kustomize 校验 | G2 |
| **app_pipeline.yml** | 仅由 mainline `workflow_call` | 五产品 Android/iOS/Web canonical 编译与 immutable App OCI evidence | G2 / 候选 |
| **pre-release-gate.yml** | `push dev1.0`、`pull_request(dev1.0 -> main)`、手动 | deploy → L3 → L4 → gamma smoke | G3→G5b |
| **app-env-device-matrix-self-hosted.yml** | `push dev1.0` / `pull_request(dev1.0 -> main)` / 被调用 / 手动 | self-hosted 动态设备矩阵唯一入口 | G5b |
| **prod-sim-manual-admission.yml** | 手动 | exact main SHA 的隔离、不可晋级 first-party 预演 | G5b 诊断 |
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
| **QWQ_ANDROID_NONPROD_GOOGLE_SERVICES_JSON** | `android-nonprod-apk` 信任域的 Firebase Provider 注册配置原文 |
| **QWQ_ANDROID_PROD_GOOGLE_SERVICES_JSON** | `android-prod-apk` 信任域的 Firebase Provider 注册配置原文 |

iOS Distribution P12、Provisioning Profile 与 ExportOptions 只属于独立的签名 IPA/商店分发 gate，
不进入本 workflow 的五产品基础编译矩阵。Flutter 不支持 iOS Release simulator；iOS 基础产品编译 unsigned iphoneos Release `.app`，Simulator 启动另走 non-promotable Debug gate。Prod iOS 正式 ID 未登记时，
该分发 gate 必须保持 `GATE_BLOCK`。

### 发布证明

- 本 workflow 不再接受 tag 或独立手动发布；只能绑定 mainline 传入的完整 Git SHA。
- Android、iOS、Web 并行构建五个 metadata-owned 产品：`android-nonprod-apk`、
  `android-prod-apk`、`ios-nonprod-app`、`ios-prod-app`、`web-shared`。每个 product job
  只调用 `stackctl package --kind app-artifact --build-product-id ...`，不直接持有 Flutter
  构建命令；Alpha/Beta/Gamma 不再触发重复编译。
- 每个产品 shard 直接写入 run/attempt 唯一的 GHCR OCI transport tag；aggregate 先将 tag
  原子解析为 digest，再只按 exact `ghcr.io/...@sha256:...` 回读并拒绝文件冲突。Actions
  Artifact 不参与 job 间交换。aggregate 要求恰好五份实际 payload 后发布唯一正式 App
  evidence OCI；后续 seal 和环境晋级只接受该 workflow 输出的 exact digest ref。
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
- `user_acceptance` Patrol 已统一迁到 **本机 macOS self-hosted runner**，通过 `flutter devices --machine` 动态发现当前可见的 Android/iOS 模拟器或真机。`03` / `04` / `05` 的 required PR 路径要求 Android 与 iOS 两个独立 job 均成功，任一平台缺席或失败都会 fail-closed。
- `main` 的 `dev1.0 -> main` promotion 合入规则中，`03` / `04` / `05` 需同时配置为 required checks；`dev1.0` direct push 会为同一精确 SHA 生成三项 integration check evidence。

---

## 六、App Env Device Matrix（app-env-device-matrix-self-hosted.yml）

### self-hosted（dev1.0 push / promotion pull_request / workflow_call / 手动统一复用）

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
| **ENABLE_SELF_HOSTED_MOBILE_MATRIX** | required PR/main 路径必须精确为 `true`；缺失或其他值均输出 `GATE_BLOCK`。仅独立 `workflow_dispatch` 且显式设置 `allow_disabled_mobile_matrix_debug=true` 时可返回不构成准出的 `result=skipped` |
| VIDEO_PLAYBACK_CANARY_WORK_ID | `environment-smoke` 当前已发布视频对象；缺失时设备矩阵 fail-closed |
| **RELEASED_RELEASE_EVIDENCE_REF** | Nightly schedule 与 Provider producer 共用的唯一稳定发现指针；值必须是 status=`released` 的 exact `ghcr.io/.../release-artifact@sha256:...`。消费端会校验完整 manifest/文件闭包、BuildKit SBOM/provenance、GitHub OIDC issuer 与 `deploy-prod-auto.yml` signer identity |

### 说明

- `app-env-device-matrix-self-hosted.yml` 已成为唯一的 **05. App Env Device Matrix** 入口；同时支持 `push dev1.0`、`pull_request(dev1.0 -> main)`、被其他 workflow 调用以及手动调试。
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
| **Android 与 iOS 双平台可见** | required PR/main 路径必须分别租约一台 Android 与一台 iOS 模拟器或真机；任一平台 job 缺席、跳过或失败，或 aggregation 未成功，矩阵都直接 `GATE_BLOCK` |

### Prod-Sim 手动准入的独立前提

`prod-sim-manual-admission.yml` 使用 `prod-sim-admission` GitHub Environment，
只生成 `nonPromotable=true` 的隔离预演证据，不构成 Prod 发布或 promotion 证据。

| 配置位置 | 名称 / 路径 | 约束 |
|----------|-------------|------|
| `prod-sim-admission` Environment variable | **PROD_SIM_SSH_MANAGEMENT_HOST** | 必须是裸 SSH host（域名或 IPv4），不得包含 scheme、端口、用户名、路径或空白 |
| self-hosted runner 本地文件 | **`~/.ssh/quwoquan-prod/prod-edge-svc`** | `prod-edge-svc` 私钥，必须为普通文件且 mode 精确 `0600` |
| self-hosted runner 本地文件 | **`~/.ssh/quwoquan-prod/prod-service-svc`** | `prod-service-svc` 私钥，必须为普通文件且 mode 精确 `0600` |

上述两个私钥是 runner-local 运维凭据，不是 GitHub Secret，也不得进入仓库、
Actions Artifact 或日志。缺 host、缺任一 key、权限漂移或 source SHA 不可达
`main` 时 workflow 必须 fail closed。

---

## 七、远端 Gamma（已退役）

远端 ECS gamma onebox 部署已退役，所有 `GAMMA_ECS_*` secret/var（`GAMMA_ECS_SSH_KEY`、`GAMMA_ECS_PASSWORD`、`GAMMA_ECS_HOST`、`GAMMA_ECS_REMOTE_DIR`、`GAMMA_ECS_CONTAINER_REGISTRY_MIRROR`、`GAMMA_ECS_*_TIMEOUT_SECONDS` 等）均不再使用。

- `gamma` 仅本地（local-gamma mirror），本地 left-shift 验证不需要任何远端 secret。
- 真实远端发布、就地升级与集成 / curated 媒体路由复验统一由 prod `canary` rollout stage 承接（见第八节 `deploy-prod-auto.yml`）。
- prod 远端访问统一走**按平面 SSH 凭据**（见第八节），不得复用任何 `GAMMA_ECS_*` 命名，亦不再使用单一全权 `PROD_KUBECONFIG`。

---

## 八、Prod Hosted Deploy（deploy-prod-auto.yml）

PR/Delivery 的打包门分两层：Alpha/Beta/Gamma 使用临时部署根真实执行 hermetic
package；Prod 只执行 fail-closed contract、artifact isolation、OCI evidence 与 purity
测试，不注入虚构法务或签名事实，也不形成 active candidate。`main` 发布事务必须在
真实 `stackctl package --env prod --target prod-hosted` 后立即执行 packaging verify；
真实 legal/signing/release evidence 任一缺失都会阻断，独立的
`verify-prod-hosted-runtime-readiness` 只用于 live legal/health/SSH plane 诊断，不是构包
或发布准出回执。

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
| **OTEL_EXPORTER_OTLP_ENDPOINT**（prod-hosted 主机变量，可选） | 服务 trace 的 OTLP/HTTP 接收端，必须是带 scheme 的绝对 URL（`http://host:port` 或 `https://host:port`，scheme 决定是否加密传输，缺 scheme 服务判否）；未设置时使用共享网络内 `http://otel-collector:4318` |
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
| `QWQ_DNS_PROVISIONING_API_TOKEN` | 权威 DNS 记录写入凭据，仅供 canonical A/AAAA/CAA/MX/TXT apply |
| `QWQ_ACME_DNS_API_TOKEN` | DNS-01 challenge 专用凭据，与 provisioning 凭据独立轮换 |
| `QWQ_PROD_EDGE_IPV4` | 生产 edge 的公网 IPv4；只在 apply 时注入，不入仓库 |
| `QWQ_TLS_AGE_RECIPIENT` | 证书部署方持有私钥的 age 公钥；CI 只上传加密后的证书包 |

变量名与 workflow 接线是供应商中立的；具体厂商只由
`quwoquan_ops/environments/domain_governance.yaml` 的 `dnsProvider.kind` 与
`acme.dnsProvider` 决定，当前现役实现是阿里云云解析（`aliyun-dns` / lego `alidns`）。
在该实现下两个 DNS 凭据的值形状为 `<accessKeyId>:<accessKeySecret>`，分别对应两个
独立 RAM 用户。凭据形状由 provider 实现解释，策略只声明「环境变量名 -> 凭据部件名」，
因此换服务商只需新增 provider 实现，secret 名、策略键与 workflow 都不变。

zone 标识不是 secret：它就是策略已声明的 `registrableDomain`，再要一份部署时输入
只会形成第二真相源。ACME 注册邮箱同理不是签发前提——Let's Encrypt 已不要求联系
邮箱，签发命令不传 `--email`，因此这里不需要任何邮箱。

两个 RAM 用户在授权面上的实际差异只有「是否独立轮换与吊销」：云解析的授权粒度到
域名为止，无法把 challenge 用户限定在 `_acme-challenge` 前缀，详见下文与 `OPEN-008`。

公网核对使用的两个 DoH 解析器都不属于权威服务商——用服务商自家解析器核对自家写入
等于自证，门禁会拦。这两个解析器只做只读取证，不构成任何服务商依赖。

现役实现下两个 RAM 用户各自的最小权限如下。两者都只勾选「编程访问」，不加控制台
登录，也不加入任何带 `AliyunDNSFullAccess` 的用户组。

provisioning 用户（`QWQ_DNS_PROVISIONING_API_TOKEN`）需要 canonical 记录集的读写
与对账能力：`alidns:DescribeDomainRecords`、`alidns:DescribeDomainRecordInfo`、
`alidns:AddDomainRecord`、`alidns:UpdateDomainRecord`、`alidns:DeleteDomainRecord`、
`alidns:SetDomainRecordStatus`，资源限定到 `quwoquan.com` 这一个域名。不要授予
域名转移、NS 变更、DNS 安全加速或账单相关动作。

challenge 用户（`QWQ_ACME_DNS_API_TOKEN`）只需要 lego 完成 DNS-01 所需的四个动作：
`alidns:DescribeDomainRecords`、`alidns:AddDomainRecord`、`alidns:UpdateDomainRecord`、
`alidns:DeleteDomainRecord`，同样限定到 `quwoquan.com`。云解析的 RAM 授权粒度到
域名为止，无法在授权层把它限定在 `_acme-challenge` 前缀，因此该范围由凭据隔离与
工具链行为保证，策略侧已如实标注为 `credential-isolation-only`，风险与三条候选收紧
路径登记在环境拓扑节点的 `OPEN-008`。

`QWQ_PROD_EDGE_IPV4` 填生产 edge 的公网 IPv4；换机时同时改这个 secret 与
`quwoquan_ops/environments/prod/access-isolation.yaml` 的 `sshHost`，前者是数据面、
后者是管理面，两者不共享同一份取值。这个地址不是机密（公网 DNS 本就可查），放
secret 的理由是换机只改注入值、不产生仓库改动。

写入生产 DNS 记录属于破坏性动作：定时触发只跑 plan 与漂移核对，覆盖或删除现存
生产记录必须手动 dispatch 并勾选 `applyProductionRecords`，否则 CLI 先行
`GATE_BLOCK` 且不产生任何 provider 写入。首次下发生产记录不需要该确认。

收敛的所有权按记录类型划定：地址（`A`/`AAAA`/`CNAME`）与 zone 级授权（`CAA`/`MX`）
由计划完全拥有，同名同类型的多余值会被清除；`TXT` 是共享类型，收敛只认自己声明的
`v=spf1` 与 `v=DMARC1`，备案与第三方站点校验令牌不会被占用或删除，只在 receipt 的
`observedUnmanaged` 里列出。因此在控制台加备案 TXT 是安全的，加第二条 apex A 记录
不是。

Workflow 不上传明文私钥；证书包以 age 加密、保留 7 天。DNS apply 与 live DNS
证据不含 token，保留 30 天。生产证书由 `public-ca-prod` profile 经同一 DNS-01
自动化签发，不再依赖仓外人工发布面。未注入 `QWQ_PROD_EDGE_IPV4` 时生产地址记录
保持缺席并在 receipt 的 `pending` 中如实报告，既不写占位值，也不删除现存记录。

---

## 十一、配置步骤

1. 进入仓库 **Settings → Secrets and variables → Actions**。
2. 点击 **New repository secret**。
3. 按上述各 Workflow 表格添加所需 Secrets。
4. 保存后，对应 push/PR/tag 或手动触发时将使用新 Secrets。
5. 若已在本机生成 prod 平面私钥，可直接自动同步并清理退役项：`bash quwoquan_ops/cli/prod/setup_prod_plane_ssh_access.sh --mode all --include-relay --include-readonly --github-sync --github-prune-obsolete-secrets`

**参考**：`quwoquan_ops/environments/prod/access-isolation.yaml`、`quwoquan_ops/environments/prod/rollout/stages.yaml`。
