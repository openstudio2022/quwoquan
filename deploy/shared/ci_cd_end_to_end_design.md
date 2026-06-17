# CI/CD 端到端闭环落实方案

> 目标：进入 `main` 前完成 pull request required checks 阻断验证；进入 `main` 后再执行发布后续动作。主干门禁统一为 `03 + 04 + 05`。

**环境拓扑总览**（alpha / beta / gamma / prod、波次关系）：见 [environment_matrix.md](environment_matrix.md)。
官方自动化入口统一为 `agent_ops/deploy/stackctl.py`；workflow、CLI、Cursor/skill 共享同一命令面与 JSON 报告契约。

## 1. 当前 Workflows

| Workflow 名称 | 文件 | 触发 | 职责 | 对应阶段 |
|---------------|------|------|------|----------|
| 03. Delivery Gate | `delivery-gate.yml` | `pull_request(main)`、手动 | PR 主门禁：拓扑、L1、L2 | G0~G3 |
| 05. App Env Device Matrix | `app-env-device-matrix-self-hosted.yml` | `pull_request(main)`、`workflow_call`、手动 | 本地 self-hosted alpha/beta Android/iOS 设备矩阵与证据校验 | G3 / G5b |
| 04. Pre-Release Gate | `pre-release-gate.yml` | `pull_request(main)`、手动 | PR 轻量 local-gamma preflight（local-gamma readiness 阻断 + smoke 漂移告警）；真实远端集成复验已下沉到 prod `gray-initial` | G3 |
| 02. Service Pipeline | `service_pipeline.yml` | `push main`、手动 | main 后 Go 构建、Python 镜像、prod 校验 | G2 / post-main |
| 07. Deploy To Prod (Auto) | `deploy-prod-auto.yml` | `push main`、手动 | main 后自动推进 prod 主链，并在 `gray-initial` 承接真实远端集成与 curated 媒体路由复验 | G5c |
| 01. App Pipeline | `app_pipeline.yml` | `v*` tag、手动 | 端侧发布构建（macOS） | 发布 |
| 06. Deploy To Prod (Gray) | 手动触发的半自动生产灰度 workflow（见 `.github/workflows`） | 手动 | 半自动灰度 | G5c |
| 09. Gamma Full Validation | `gamma-full-validation.yml` | 每晚 22:00 UTC+8、手动 | Nightly 全量验证：local-gamma full semantic smoke + Patrol UI + 设备矩阵（远端 gamma 已退役，无远端 ECS deploy） | G5b |

## 2. 进入 `main` 的主链

```text
feature / dev1.0
  → 用户显式发起到 main 的 PR
  → PR required checks
      ├─ 03 Delivery Gate
      ├─ 05 App Env Device Matrix（alpha/beta，本地 self-hosted Android+iOS，pr_light profile）
      └─ 04 Pre-Release Gate（轻量 gamma preflight：readiness 阻断，smoke 仅告警）
  → 全部通过后进入 main
  → main post-merge:
      ├─ 02 Service Pipeline
      └─ 07 Deploy To Prod (Auto)
```

## 3. 统一验证 Profile 模型

所有门禁和脚本统一消费 `deploy/shared/gamma_validation_suites.json` 中的 profile 定义：

| Profile | 用途 | 部署 gamma | readiness 阻断 | smoke 阻断 | UI 旅程 | 设备矩阵 |
|---------|------|-----------|---------------|-----------|---------|---------|
| `pr_light` | PR 默认 | 否（探针 local-gamma） | 是 | 否（漂移告警） | 无 | alpha/beta, allow_missing |
| `manual_full` | 手动触发 | 是（local-gamma full） | 是 | 是 | 无 | gamma, allow_missing |
| `nightly_full` | 每晚 22:00 自动 | 是（local-gamma full） | 是 | 是 | 全量 Patrol UI | gamma, require_all |
| `release_candidate` | 发布前回归 | 是 | 是 | 是 | 全量 Patrol UI | gamma, require_all |

> 远端真实集成 / curated 媒体路由复验不再由 gamma profile 承担，已下沉到 prod `gray-initial`（见 `07`）。

## 3.1 Stackctl 对应关系

| 能力 | 统一入口 |
|---|---|
| 环境包 | `stackctl package --env <env> [--include-services]` |
| 本地起停 | `stackctl up --env <alpha|beta|gamma|prod-sim|prod>`；底层 target 仍为 `alpha-local|beta-local|gamma-local|prod-hosted` |
| 拓扑/打包/纯度校验 | `stackctl verify --env <env>` |
| 健康检查 | `stackctl health --target <target>` |
| 巡检 | `stackctl inspect --target <target> --scope logs|network|data|metrics|config|security|all` |
| 聚合诊断 | `stackctl doctor --target <target>` |
| 修复 | `stackctl repair --target <target> --fix <class>` |
| hosted prod rollout（唯一远端目标） | `stackctl deploy --target prod-hosted --service <svc> --from-image <old> --to-image <new> --from-config <old_cfg> --to-config <new_cfg> --step <step> --error-rate <rate> --p95-ms <ms> --redis-error-rate <rate>` |

## 4. `04` / `05` / `09` 的职责分工

### 4.1 `04. Pre-Release Gate`

PR 轻量 local-gamma preflight（默认 `pr_light` profile）：

1. 对 local-gamma mirror 执行探针：
   - local-gamma readiness（/healthz + product-ops + 路由）→ **阻断**
   - assistant protocol smoke → 漂移告警（不阻断）
   - chat avatar API probe → 漂移告警（不阻断）
2. 支持通过 `workflow_dispatch` 的 `validation_profile=manual_full` 触发完整 local-gamma 复验链。
3. 真实远端集成 / curated 媒体路由复验不在 PR 阶段执行，已下沉到 prod `gray-initial`（`07`）。
4. readiness、artifact purity、routing 证据必须可通过 `stackctl health/inspect/doctor` 复放。

### 4.2 `05. App Env Device Matrix`

本地 self-hosted 设备矩阵唯一入口（支持 `validation_profile` 分层）：

- PR 默认 `pr_light`：alpha/beta 环境，`allow_missing_platforms=true`。
- `nightly_full`：alpha/beta/gamma 全环境，`require_all_platforms`。
- `manual_full`：gamma 单环境，`allow_missing_platforms=false`。
- 通过 `flutter devices --machine` 动态发现设备。
- alpha/beta 环境包与 public URL 由 `stackctl package --env alpha|beta` 统一生成。

### 4.3 远端 gamma 部署（已退役）

旧 `08. Deploy Gamma ECS` 远端 ECS gamma 部署与 prod 复验链已退役。真实远端发布、就地升级与 prod 复验统一由 `07. Deploy To Prod (Auto)` 在 `gray-initial -> carry-on/checks -> full` rollout stage 完成；`gray-initial` 同时承接旧 gamma-hosted 的 readiness、T3 API contract、chat avatar probe 等真实远端集成与 curated 媒体路由复验。等价 CLI 入口：`stackctl deploy --target prod-hosted ...`。

### 4.4 `09. Gamma Full Validation`

Nightly 全量验证（每晚 22:00 UTC+8 = cron `0 14 * * *`），全部针对 local-gamma：

- local-gamma full semantic 复验（`full_semantic` profile，无远端 ECS deploy）
- Patrol full UI profile（全量 UI 旅程）
- gamma assistant 设备矩阵（`nightly_full` profile）
- gamma chat-avatar 设备矩阵（`nightly_full` profile）
- `stackctl inspect --target gamma-local --scope all` 报告归档到 nightly artifact。

## 5. 依赖与前置

### 5.1 GitHub Secrets / Variables

| 名称 | 用途 |
|------|------|
| `secrets.PROD_EDGE_SSH_KEY` / `PROD_MEDIA_SSH_KEY` / `PROD_SERVICE_SSH_KEY` | prod-hosted 发布三平面读写 SSH 私钥（`07` 使用） |
| `GAMMA_TEST_AUTH_TOKEN` | local-gamma / self-hosted 链路鉴权 |
| `gamma_base_url` workflow input / 本地环境变量覆盖 | 仅在需要覆盖 topology `gamma-local.publicBases.api` 时使用 |
| `vars.MEDIA_AVATAR_CDN_BASE_URL` | chat-avatar 媒体基址 |
| `vars.ENABLE_SELF_HOSTED_MOBILE_MATRIX` | 控制 PR 是否启用 self-hosted 设备矩阵 |

远端 gamma 已退役，不再需要任何 `GAMMA_ECS_*` secret/var。完整矩阵见 [environment_matrix.md](environment_matrix.md)。

### 5.2 Self-hosted Runner

- 统一使用当前开发机注册的 `self-hosted` + `macOS` runner。
- 设备发现通过 `flutter devices --machine` 动态完成。
- PR 默认允许缺席平台跳过（`pr_light`）；nightly/release 要求全平台通过。
- artifact 必须包含设备清单、原始日志、命令清单与截图/失败截图。

### 5.3 local-gamma 活性

- gamma 仅本地（local-gamma mirror），无远端共享 gamma 需要长期维护。
- PR `04` 在 runner 内对 local-gamma 做 readiness 探针；起栈失败即快速失败并发出修复信号。
- 真实远端可用性在 prod `gray-initial` rollout stage 通过 `stackctl health/inspect/doctor` 复验。

## 6. 验证清单

1. `main` 分支保护中 required checks 配置为 `03`、`04`、`05`。
2. `04` 默认轻量探针 local-gamma：readiness 阻断，smoke 仅告警。
3. `05` PR 默认 alpha/beta `pr_light` profile，允许缺席平台跳过。
4. 远端真实集成 / curated 媒体路由复验由 `07` 在 prod `gray-initial` 承接（远端 gamma 已退役）。
5. `09` nightly 22:00 自动执行全量验证（local-gamma full semantic + Patrol UI + 全设备矩阵）。
6. `deploy/shared/gamma_validation_suites.json` 是 profile/suite 唯一真相源。
7. 门禁脚本 `verify_gamma_validation_profiles.py`、`verify_ci_profile_consistency.py`、`verify_environment_topology_manifest.py`、`verify_local_env_port_manifest.py`、`verify_public_vs_upstream_url_contract.py`、`verify_environment_packaging_contract.py`、`verify_env_artifact_isolation.py`、`verify_prod_package_purity.py` 已串联 `make gate` 或 `stackctl verify`。
8. T1~T4 证据均可从 `artifacts/stackctl/**`、`artifacts/local-gamma/**`、workflow artifact 回放。

## 7. 参考

- `deploy/shared/environment_matrix.md`
- `deploy/shared/branch_strategy.md`
- `deploy/shared/deliver_to_production_runbook.md`
- `deploy/shared/workflow_consolidation_plan.md`
- `deploy/shared/gamma_validation_suites.json`
- `.github/workflows/pre-release-gate.yml`
- `.github/workflows/app-env-device-matrix-self-hosted.yml`
- `.github/workflows/gamma-ecs-pre-hosted-core.yml`
- `.github/workflows/gamma-pr-hosted-core.yml`
- `.github/workflows/gamma-full-validation.yml`
