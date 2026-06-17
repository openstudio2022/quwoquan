# Deliver → Prod 端到端运行手册

**环境拓扑链与 prod rollout stage** 见 [environment_matrix.md](environment_matrix.md)（与本文阶段编号一致：alpha / beta / gamma / prod，其中 `local-gamma mirror` 是 `gamma` 的本地左移拓扑，不是额外环境）。

## 1. 目标

从特性到入库（L1/L2 自测通过），再到集成验证（L3/L4），再到生产端到端打通，含灰度/滚动发布。

```
特性 → dev 完成本地 T1/T2/T3/T4 左移验证并自动归档 → commit 入库 → PR required checks（03/04/05）→ 灰度到 prod（`gray-initial` 承接真实远端集成验证）
```

---

## 2. 阶段划分

| 阶段 | 命令/动作 | 门禁 | 输出 |
|------|-----------|------|------|
| 1. 开发+入库 | `/dev` → `/commit`（或 `/deliver`） | G2 → G3 → G4 | `/dev` 完成四层自验证、gray-release ready 与自动归档；`/commit` 前本地 `gate-local-gamma` 通过并完成入库 |
| 2. PR 主门禁 | `03` / `04`（pr_light）/ `05`（pr_light） | G5a | local-gamma readiness 通过 + alpha/beta 设备矩阵通过 |
| 3. 集成验证收口 | `09`（nightly_full） | G5b | local-gamma full semantic smoke + Patrol UI + 全设备矩阵通过 |
| 4. 灰度到 prod | `config-gray-rollout` | G5c | prod 灰度完成（`gray-initial` 承接真实远端集成与 curated 媒体路由复验），SLO 通过 |

---

## 3. 前置条件

### 3.1 Deliver 阶段完成

- 代码已合入 `dev1.0`（分支开发模式）或已准备发起进入 `main` 的 PR；分支策略见 `deploy/shared/branch_strategy.md`
- `make gate-local-gamma` 建议在提交前通过并生成 `artifacts/local-gamma/report.json`。该命令用于左移预测试，不替代 `main` 的 required checks；见 `/.cursor/commands/commit.md`
- `deploy/shared/process_domain_mapping.yaml` 合法，`verify_deployment_domain_mapping.sh` 通过
- `deploy/shared/environment_topology_manifest.yaml`、`deploy/shared/local_env_port_manifest.yaml` 已通过校验
- 如变更环境打包/启动/发布链路，先执行 `python3 agent_ops/deploy/stackctl.py verify`

### 3.1.1 local-gamma mirror（提交前左移）

提交前必须先在本机运行 local-gamma mirror：

```bash
make gate-local-gamma
# 或统一入口
python3 agent_ops/deploy/stackctl.py up --env gamma
```

通过判据：

- `T1`：metadata、拓扑、环境包、seed manifest、错误码、静态语义与生成物校验通过。
- `T2`：Flutter/Go/Ops 模块、Widget、Provider/Journey 测试通过。
- `T3`：本地 gamma 镜像栈真实 API、真实存储副作用、错误响应与 RemoteRepository smoke 通过。
- `T4`：复用共享 gamma 旅程脚本；若当前可见多台设备则全部执行，本地左移至少需要一台可用设备进入验证。
- 报告：`artifacts/local-gamma/report.json` 状态为 `passed`。

缺少本地 DNS/TLS、设备、服务依赖或 seed/reset 能力时，状态必须为 `GATE_BLOCK`，不得继续提交。

### 3.1.2 多环境多实例口径

- 端侧 `alpha` / `beta` / `gamma` 可在**不同模拟器**并行运行多个实例。
- 每次启动必须显式绑定唯一 `device-id`，避免交互式 `flutter run` 争用全局 Flutter startup lock。
- `beta` 服务端只允许一套本地集成栈；重新启动 beta 前必须停止旧实例并回收固定端口。
- `gamma` 服务端只允许一套 local-gamma mirror（无远端 gamma）；mirror 切换必须先清理旧实例再重启。
- 本手册中的“多实例”仅指端侧 App 进程，不代表服务端允许多套 beta/gamma 并行。

### 3.2 部署环境

- **gamma（仅本地）**：local-gamma mirror 可访问；默认 URL 从 topology `gamma-local.publicBases.*` 解析，仅 `GAMMA_TEST_AUTH_TOKEN` 作为可选鉴权 secret（无远端 gamma）
- **prod（唯一远端目标）**：`CONFIG_VERSION`、`IMAGE_VERSION` 已确定；backend 为 `ssh-hosted + rootless podman compose`，gray 与 full 共享同一物理 ECS
- **多云切换**：通过 `CLOUD_PROVIDER=aliyun|volcengine|huaweicloud` 选择 overlay，见 `deploy/cloud-providers/`

### 3.2.1 Package Purity / Host Allowlist

进入 G5c 前必须确认：

- 已执行 `python3 agent_ops/deploy/stackctl.py package --env prod --include-services`
- 已执行 `python3 agent_ops/deploy/stackctl.py verify --env prod`
- prod artifact 不包含 mock/seed/debug/test/local host
- prod host allowlist、secret scope 与 rollout stage 由 `environment_topology_manifest.yaml` 驱动，不能手工覆盖出第二套口径

### 3.3 灰度参数

- `FROM_IMAGE`、`TO_IMAGE`：当前与目标镜像版本
- `FROM_CONFIG`、`TO_CONFIG`：当前与目标配置版本
- `STEP`：当前 2 副本为 50（初始灰度 1 pod，全自动）→ 100（Carry-on 全量，需审批）。初始灰度 pod 数可配置；副本增加时可扩展中间阶段。

### 3.4 版本号从哪里获取（图一表单四个字段）

**要区分两个东西**：

- **`state/release/seed-box.state`** 是**状态文件**，记录「上一次灰度完成后 prod 正在跑的版本」：里面的 `to_image`、`to_config` 就是**当前 prod** 的镜像/配置版本。表单里的 **Current prod** 应从**这个 state 文件**取，不是从 `releases/config/` 取。
- **`releases/config/seed-box/v*.yaml`** 是**某次发布用的配置内容**（该版本的配置快照），用于校验「目标配置版本」是否存在；不表示“当前 prod 版本号”。

| 字段 | 含义 | 获取方式 |
|------|------|----------|
| **Current prod image version** | 当前生产正在使用的镜像版本 | 从 **`state/release/seed-box.state`** 的 **`to_image`** 读取（上次灰度完成后写入）；若无则 SSH 到 prod ECS（`prod-service-svc`）查：`podman inspect -f '{{index .Config.Labels "org.opencontainers.image.version"}}' quwoquan-service-prod_seed-box_1`（远端为 ssh-hosted + rootless podman compose，已退役 kubectl/`PROD_KUBECONFIG`） |
| **Target image version (match pre-release)** | 本次要上的镜像版本，须与预发布一致 | 来自 **main PR required checks（`04. Pre-Release Gate`）通过的构建版本**：tag 触发用该 tag 或解析值；必要时参考 service pipeline build report / workflow artifact |
| **Current prod config version** | 当前生产正在使用的配置版本 | 从 **`state/release/seed-box.state`** 的 **`to_config`** 读取；若无则从 deployment 环境变量 `CONFIG_VERSION` 读取 |
| **Target config version** | 本次要上的配置版本 | 与 target image 对应，来自 pre-release 的 `CONFIG_VERSION`（同上） |

**约定**：Target 必须与 `04. Pre-Release Gate` 通过的构建版本一致。Workflow 支持**留空 Current prod 两栏**时自动从 `state/release/seed-box.state` 读取（见下文）。

---

## 4. G5a：本地 left-shift 验证（远端 gamma pre 已退役）

旧的「部署到 ECS gamma pre」阶段已随远端 gamma 退役而移除。提交前的端云预验证统一在本地 local-gamma mirror 完成（见 3.1.1），真实远端发布与集成复验下沉到 prod `gray-initial`（见 §6）。

1) 提交前左移在本机运行 local-gamma mirror：

```bash
make gate-local-gamma
# 或统一入口
python3 agent_ops/deploy/stackctl.py up --env gamma
```

2) local-gamma mirror 执行：

- 启动与 prod 同构的本地工作负载图谱
- assistant gamma smoke
- gamma API contract
- chat-avatar API probe

3) 真实远端可达性在 prod `gray-initial` rollout stage 校验（统一入口 `stackctl deploy --target prod-hosted ...`）：

```bash
python3 agent_ops/deploy/stackctl.py deploy --target prod-hosted --service seed-box --from-image <old> --to-image <new> --from-config <old> --to-config <new> --step 50 --error-rate <rate> --p95-ms <ms> --redis-error-rate <rate>
```

---

## 5. G5b：T3/T4 集成验证

### 5.1 T3 API Contract

```bash
API_CONTRACT_ENV=gamma \
GAMMA_TEST_AUTH_TOKEN=<token> \
make test-api-contract
```

如需覆盖默认 local-gamma 入口，再额外传：

```bash
GAMMA_BASE_URL=<gamma-api-url> \
GAMMA_PRODUCT_OPS_BASE_URL=<gamma-product-ops-url>
```

失败 → 不得进入 G5c。

### 5.2 T4 self-hosted 设备旅程（真机/模拟器）

```bash
python3 scripts/run_assistant_device_matrix_ci.py --platform android
python3 scripts/run_assistant_device_matrix_ci.py --platform ios
python3 agent_ops/avatar/run_chat_avatar_device_matrix_ci.py --platform android
python3 agent_ops/avatar/run_chat_avatar_device_matrix_ci.py --platform ios
```

CI 使用 `.github/workflows/pre-release-gate.yml` 与 `.github/workflows/app-env-device-matrix-self-hosted.yml` 在本机 macOS self-hosted runner 上动态发现当前可见的 Android/iOS 设备，并要求两个平台都通过。artifact 必须包含设备清单、原始日志、命令清单与截图证据。

失败 → 不得进入 G5c。

### 5.3 端侧多模拟器并行验证

若本次变更触及多环境启动链路，应额外验证：

```bash
scripts/start_app_instance.sh --env alpha --device-id <alpha-device>
scripts/start_app_instance.sh --env beta --device-id <beta-device>
scripts/start_app_instance.sh --env gamma --device-id <gamma-device>
```

通过判据：

- 三个实例位于不同模拟器；
- beta/gamma 未派生第二套服务端栈；
- beta 重新启动时会先 stop 旧栈；
- gamma 仅附着到同一套 local-gamma mirror（无远端 gamma）。

---

## 6. G5c：灰度/滚动发布到 prod

### 6.0 灰度对象：整颗 seed-box（不按服务区分）

在 **integration / prod** 只有一个发布单元：**seed-box**，内有两个容器（Go seed-box + Python recommendation-service），**一起发布、同一镜像/配置版本**。灰度就是整颗 seed-box 一起滚，不按“服务”拆开。配置与状态统一用 seed-box：`releases/config/seed-box/`、`state/release/seed-box.state`。

> **远端底座（prod-hosted）现状**：成本约束下 prod 与原 gamma 同台 ECS，远端发布为 **ssh-hosted + rootless podman compose**（非独立 ACK 集群），按 `edge/media/service/data` 四平面去 root 隔离（账号 `prod-<plane>-svc`，见 `deploy/shared/prod_plane_access_isolation.yaml`），seed-box 归属 `service` 平面、由 `prod-service-svc` 发布。`deploy/service/seed-box/kustomize/**` 与 `deploy/kustomization/<cloud>-prod` 保留为面向未来 ACK 的脚手架（仅静态门禁校验），当前不参与远端 apply。
>
> **当前端口与内存约束（2026-06-18 复核）**：`gray-initial` 命名空间固定暴露 `29000/29010/29100/29110`（TLS/Admin=`28443/22019`），`full` 命名空间固定暴露 `19000/19010/19100/19110`（TLS/Admin=`18443/12019`）。现网 ECS 仅 `2G`，gray 只作为短驻验证面保留；完成 `health + inspect + doctor + SLO` 并切 full 后应及时回收 gray。若发布窗口需要与旧 root 数据面短时共存，Mongo 必须带 `wiredTigerCacheSizeGB=0.25`，否则容易被 OOM killer 回收。

### 6.1 灰度步进

每步执行（灰度对象固定为 seed-box）：

```bash
make config-gray-rollout \
  SERVICE=seed-box \
  FROM_IMAGE=<old> TO_IMAGE=<new> \
  FROM_CONFIG=<old> TO_CONFIG=<new> \
  STEP=5  # 当前 gray-initial；100 为 full。最终以 rollout stage policy/stackctl 映射为准。

# 或统一入口
python3 agent_ops/deploy/stackctl.py deploy \
  --target prod-hosted \
  --service seed-box \
  --from-image <old> --to-image <new> \
  --from-config <old> --to-config <new> \
  --step 5 \
  --error-rate <rate> \
  --p95-ms <ms> \
  --redis-error-rate <rate>
```

### 6.2 SLO 卡点（每步后）

```bash
make config-slo-gate \
  ERROR_RATE=<实测> P95_MS=<实测> REDIS_ERROR_RATE=<实测>
```

建议同时归档：

```bash
python3 agent_ops/deploy/stackctl.py health --target prod-hosted
python3 agent_ops/deploy/stackctl.py inspect --target prod-hosted --scope all
python3 agent_ops/deploy/stackctl.py doctor --target prod-hosted
```

本轮通过的真实证据：

- `gray-initial`: `artifacts/stackctl/prod/20260617T164119Z-deploy-prod-hosted`（`OK: stage=5 decision=continue`，post-deploy `4/4 healthy`，doctor 无问题）。
- `full`: `artifacts/stackctl/prod/20260617T172537Z-deploy-prod-hosted`（`OK: stage=100 decision=continue`，post-deploy `4/4 healthy`，doctor 无问题）。
- 当前稳态复核：`artifacts/stackctl/prod/20260617T173159Z-verify-prod-hosted`、`artifacts/stackctl/prod/20260617T173201Z-doctor-prod-hosted`。

阈值见 `deploy/service/config-release/slo_thresholds.yaml`。

### 6.2.1 登录与账号商用卡点

触及登录、会话、账号安全、隐私权利、Web 登录入口时，进入 G5c 前必须额外归档：

- `make verify-app-auth-policy`
- `make verify-app-login-entry-loop-contract`
- `flutter test test/cloud/runtime/cloud_http_client_refresh_test.dart test/core/auth/auth_session_controller_test.dart test/app/app_startup_welcome_test.dart`
- `flutter test test/ui/settings/pages/settings_page_appearance_test.dart test/app/shell/web_auth_entry_contract_test.dart`
- user-service `auth_contract_test.go`、`credential_contract_test.go`、`persona_contract_test.go` 的 gamma 证据

认证账号链路 SLO：

- 欢迎页到首页 P95 <= 2s
- OTP 发码 P95 <= 1.5s
- 登录成功到目标页 P95 <= 2s
- token refresh + retry P95 <= 800ms
- 设置账号安全首屏 P95 <= 1.5s
- 凭证绑定/解绑、注销/恢复、拉黑/举报等危险动作 P95 <= 2s

No-Go 条件：

- 账号注销、数据导出、撤回同意、恢复申诉仍只有“待接入”入口或无后端闭环。
- 法律文本 URL / 版本 / consent record 不可审计。
- `Logout` / `BindCredential` / `UnbindCredential` / 设置类 owner API 在 metadata 或生成鉴权快照中不是 `required`。
- 会话过期后无法 refresh once + retry，或 refresh 401 后不能清 session 并进入安全重登。
- Web 宽屏消息/我的入口与移动端强入口登录契约不一致。

### 6.3 异常回滚

```bash
make config-rollback SERVICE=seed-box TO_CONFIG=<rollback-version>
```

若需要统一修复入口：

```bash
python3 agent_ops/deploy/stackctl.py repair --target prod-hosted --fix rebuild-packages
```

### 6.4 high_risk_fields

变更 `deploy/service/config-release/high_risk_fields.yaml` 中字段时，须：

- 审批（min_approvers: 2）
- 灰度（require_gray_release: true）
- 回滚方案（require_rollback_plan: true）

---

## 7. 端到端检查清单

```
☐ deliver 完成，代码已入库 `dev1.0` 或已准备进入 `main` 的显式 PR（分支策略见 `branch_strategy.md`）
☐ make gate-local-gamma 通过（本地 T1/T2/T3/T4）并生成 artifacts/local-gamma/report.json
☐ verify_deployment_domain_mapping.sh 通过
☐ environment_topology / local_env_port manifest 校验通过
☐ stackctl package / verify 报告已归档
☐ `03` / `04` / `05` required checks 已全部通过
☐ local-gamma left-shift 已验证目标版本（远端 gamma pre 已退役，远端验证在 prod gray-initial）
☐ T3 test-api-contract 通过
☐ local-gamma assistant/avatar Android+iOS 旅程通过并带证据产物
☐ prod package purity / artifact isolation / public-vs-upstream URL 契约通过
☐ 灰度：初始灰度（1 pod，全自动）→ Carry-on 100%（审批后执行）
☐ 每步 SLO 卡点通过
☐ prod 100% 后监控稳定
```

---

## 8. 参考

- `specs/00_MASTER_DEVELOPMENT_FLOW.md` — 主流程（含 Deploy 阶段 G5）
- `deploy/shared/branch_strategy.md` — **分支策略**（显式 PR + required checks）
- `deploy/shared/ci_cd_end_to_end_design.md` — **CI/CD 端到端闭环落实方案**（pre-release workflow、secrets、实施顺序）
- `deploy/shared/workflow_consolidation_plan.md` — **Workflow 命名规范**（01～08、PR/main-only）
- `.cursor/commands/deploy.md` — 部署命令
- `deploy/shared/process_domain_mapping_runbook.md` — 部署拓扑
- `deploy/service/config-release/runbook.md` — 配置发布与灰度
- `specs/feature-tree/runtime/deliver-deploy-prod-pipeline/design.md` — 多云（阿里云/火山引擎/华为云）设计
