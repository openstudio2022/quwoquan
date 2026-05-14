# CI/CD 端到端闭环落实方案

> 目标：进入 `main` 前完成 pull request required checks 阻断验证；进入 `main` 后再执行发布后续动作。主干门禁统一为 `03 + 04 + 05`。

**五环境总览**（alpha / beta / gamma / prod-gray / prod、波次关系）：见 [environment_matrix.md](environment_matrix.md)。

## 1. 当前 Workflows

| Workflow 名称 | 文件 | 触发 | 职责 | 对应阶段 |
|---------------|------|------|------|----------|
| 03. Delivery Gate | `delivery-gate.yml` | `pull_request(main)`、手动 | PR 主门禁：拓扑、L1、L2 | G0~G3 |
| 05. App Env Device Matrix | `app-env-device-matrix-self-hosted.yml` | `pull_request(main)`、`workflow_call`、手动 | 本地 self-hosted alpha/beta Android/iOS 设备矩阵与证据校验 | G3 / G5b |
| 04. Pre-Release Gate | `pre-release-gate.yml` | `pull_request(main)`、手动 | PR 轻量 gamma preflight（共享 gamma readiness 阻断 + smoke 漂移告警）；显式 manual_full 可触发完整 ECS 链 | G3 |
| 02. Service Pipeline | `service_pipeline.yml` | `push main`、手动 | main 后 Go 构建、Python 镜像、prod 校验 | G2 / post-main |
| 07. Deploy To Prod (Auto) | `deploy-prod-auto.yml` | `push main`、手动 | main 后自动推进 prod 占位链路 | G5c |
| 01. App Pipeline | `app_pipeline.yml` | `v*` tag、手动 | 端侧发布构建（macOS） | 发布 |
| 06. Deploy To Prod (Gray) | `deploy-prod-gray.yml` | 手动 | 半自动灰度 | G5c |
| 08. Deploy Gamma ECS | `deploy-gamma-ecs.yml` | 手动 | ECS gamma / onebox 手动发布与 prod 复验（完整 ECS pre 链 + prod 升级） | G5a → G5b |
| 09. Gamma Full Validation | `gamma-full-validation.yml` | 每晚 22:00 UTC+8、手动 | Nightly 全量验证：完整 ECS deploy + full semantic smoke + Patrol UI + 设备矩阵 | G5b |

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
| `pr_light` | PR 默认 | 否（探针共享 gamma） | 是 | 否（漂移告警） | 无 | alpha/beta, allow_missing |
| `manual_full` | 手动 08 触发 | 是（ECS full deploy） | 是 | 是 | 无 | gamma, allow_missing |
| `nightly_full` | 每晚 22:00 自动 | 是（ECS full deploy） | 是 | 是 | 全量 Patrol UI | gamma, require_all |
| `release_candidate` | 发布前回归 | 是 | 是 | 是 | 全量 Patrol UI | gamma, require_all |

## 4. `04` / `05` / `08` / `09` 的职责分工

### 4.1 `04. Pre-Release Gate`

PR 轻量 gamma preflight（默认 `pr_light` profile）：

1. 通过 `gamma-pr-hosted-core.yml` 探针已运行的共享 gamma：
   - gamma readiness（/healthz + product-ops + 公网路由）→ **阻断**
   - assistant protocol smoke → 漂移告警（不阻断）
   - chat avatar API probe → 漂移告警（不阻断）
2. 支持通过 `workflow_dispatch` 的 `validation_profile=manual_full` 显式触发完整 ECS 链（调用 `gamma-ecs-pre-hosted-core.yml`）。
3. 共享 gamma 的活性由 09 nightly deploy 保障；gamma 宕机时 04 会快速失败（readiness timeout），发出修复信号。

### 4.2 `05. App Env Device Matrix`

本地 self-hosted 设备矩阵唯一入口（支持 `validation_profile` 分层）：

- PR 默认 `pr_light`：alpha/beta 环境，`allow_missing_platforms=true`。
- `nightly_full`：alpha/beta/gamma 全环境，`require_all_platforms`。
- `manual_full`：gamma 单环境，`allow_missing_platforms=false`。
- 通过 `flutter devices --machine` 动态发现设备。

### 4.3 `08. Deploy Gamma ECS`

手动完整验证与发布复验：

- preflight 检查（验证 03/04/05 已通过）
- 调用 `gamma-ecs-pre-hosted-core.yml`（完整 ECS deploy + readiness + API contract + smoke）
- pre 门禁通过后执行 ECS prod 就地升级
- prod 后运行 T3 API contract + chat avatar probe + self-hosted 设备矩阵（`manual_full` profile）

### 4.4 `09. Gamma Full Validation`

Nightly 全量验证（每晚 22:00 UTC+8 = cron `0 14 * * *`）：

- 调用 `gamma-ecs-pre-hosted-core.yml`（`full_semantic` profile）
- Patrol full UI profile（全量 UI 旅程）
- gamma assistant 设备矩阵（`nightly_full` profile）
- gamma chat-avatar 设备矩阵（`nightly_full` profile）

## 5. 依赖与前置

### 5.1 GitHub Secrets / Variables

| 名称 | 用途 |
|------|------|
| `GAMMA_ECS_PASSWORD` 或 `GAMMA_ECS_SSH_KEY` | ECS gamma 部署认证（`08` / `09` 必需其一） |
| `GAMMA_TEST_AUTH_TOKEN` | gamma hosted/self-hosted 鉴权 |
| `vars.GAMMA_ECS_HOST` / `vars.GAMMA_ECS_PUBLIC_HOST` | ECS 主机与公网入口 |
| `vars.GAMMA_BASE_URL` / `vars.GAMMA_PRODUCT_OPS_BASE_URL` | 可选 URL 覆盖 |
| `vars.MEDIA_AVATAR_CDN_BASE_URL` | chat-avatar 媒体基址 |
| `vars.ENABLE_SELF_HOSTED_MOBILE_MATRIX` | 控制 PR 是否启用 self-hosted 设备矩阵 |

完整矩阵见 [environment_matrix.md](environment_matrix.md)。

### 5.2 Self-hosted Runner

- 统一使用当前开发机注册的 `self-hosted` + `macOS` runner。
- 设备发现通过 `flutter devices --machine` 动态完成。
- PR 默认允许缺席平台跳过（`pr_light`）；nightly/release 要求全平台通过。
- artifact 必须包含设备清单、原始日志、命令清单与截图/失败截图。

### 5.3 共享 Gamma 活性

- 共享 gamma 由 09 nightly deploy 每晚 22:00 UTC+8 自动刷新部署。
- 如果 gamma 在两次 nightly 之间宕机，04 会因 readiness 失败阻断 PR，发出修复信号。
- 手动恢复：通过 08 `workflow_dispatch` 重新部署 gamma。

## 6. 验证清单

1. `main` 分支保护中 required checks 配置为 `03`、`04`、`05`。
2. `04` 默认轻量探针共享 gamma：readiness 阻断，smoke 仅告警。
3. `05` PR 默认 alpha/beta `pr_light` profile，允许缺席平台跳过。
4. `08` 手动触发完整 ECS deploy + prod 复验。
5. `09` nightly 22:00 自动执行全量验证（ECS deploy + full semantic + Patrol UI + 全设备矩阵）。
6. `deploy/shared/gamma_validation_suites.json` 是 profile/suite 唯一真相源。
7. 门禁脚本 `verify_gamma_validation_profiles.py` 和 `verify_ci_profile_consistency.py` 已串联 `make gate`。

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
