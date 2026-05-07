# CI/CD 端到端闭环落实方案

> 目标：进入 `main` 前完成 pull request required checks 阻断验证；进入 `main` 后再执行发布后续动作。主干门禁统一为 `03 + 04 + 05`。

**五环境总览**（alpha / beta / gamma / prod-gray / prod、波次关系）：见 [environment_matrix.md](environment_matrix.md)。

## 1. 当前 Workflows

| Workflow 名称 | 文件 | 触发 | 职责 | 对应阶段 |
|---------------|------|------|------|----------|
| 03. Delivery Gate | `delivery-gate.yml` | `pull_request(main)`、手动 | PR 主门禁：拓扑、L1、L2 | G0~G3 |
| 05. App Env Device Matrix | `app-env-device-matrix-self-hosted.yml` | `pull_request(main)`、`workflow_call`、手动 | 本地 self-hosted alpha/beta Android/iOS 设备矩阵与证据校验 | G3 / G5b |
| 04. Pre-Release Gate | `pre-release-gate.yml` | `pull_request(main)`、手动 | ECS gamma hosted pre 链 + 本地 gamma Android/iOS assistant/avatar 旅程 | G3 → G5b |
| 02. Service Pipeline | `service_pipeline.yml` | `push main`、手动 | main 后 Go 构建、Python 镜像、prod 校验 | G2 / post-main |
| 07. Deploy To Prod (Auto) | `deploy-prod-auto.yml` | `push main`、手动 | main 后自动推进 prod 占位链路 | G5c |
| 01. App Pipeline | `app_pipeline.yml` | `v*` tag、手动 | 端侧发布构建（macOS） | 发布 |
| 06. Deploy To Prod (Gray) | `deploy-prod-gray.yml` | 手动 | 半自动灰度 | G5c |
| 08. Deploy Gamma ECS | `deploy-gamma-ecs.yml` | 手动 | ECS gamma / onebox 手动发布与 prod 复验 | G5a → G5b |

## 2. 进入 `main` 的主链

```text
feature / dev1.0
  → 用户显式发起到 main 的 PR
  → PR required checks
      ├─ 03 Delivery Gate
      ├─ 05 App Env Device Matrix（alpha/beta，本地 self-hosted Android+iOS）
      └─ 04 Pre-Release Gate（ECS gamma hosted pre + gamma 本地 Android+iOS）
  → 全部通过后进入 main
  → main post-merge:
      ├─ 02 Service Pipeline
      └─ 07 Deploy To Prod (Auto)
```

## 3. `04` / `05` / `08` 的职责分工

### 3.1 `04. Pre-Release Gate`

`04` 已收口为 **ECS gamma 主门禁**：

1. 复用 `gamma-ecs-pre-hosted-core.yml` 完成 hosted pre 链：
   - 打包 gamma ECS bundle
   - 部署 ECS pre
   - assistant gamma smoke
   - gamma API contract
   - chat avatar API probe
2. 在本地 `self-hosted + macOS` runner 上执行：
   - gamma assistant / Android
   - gamma assistant / iOS
   - gamma chat avatar / Android
   - gamma chat avatar / iOS
3. summary job 下载 artifact，校验设备清单、原始日志、命令清单和截图证据真实存在。

### 3.2 `05. App Env Device Matrix`

`05` 是 **alpha/beta 本地设备矩阵唯一入口**：

- 只在 `pull_request(main)`、`workflow_call`、手动路径运行。
- 统一使用 `self-hosted + macOS` runner。
- 通过 `flutter devices --machine` 动态发现设备。
- **Android 与 iOS 都必须存在且都成功**；不再接受“某一平台缺席但另一平台通过”的口径。
- summary job 同样会下载 artifact 并校验证据。

### 3.3 `08. Deploy Gamma ECS`

`08` 只保留 **手动 wrapper**：

- `gate` + alpha/beta 本地矩阵
- 复用与 `04` 相同的 `gamma-ecs-pre-hosted-core.yml`
- pre 门禁通过后，继续执行 ECS prod 就地升级与 prod 烟测

## 4. 本地 left-shift 与 local-gamma

- `local-gamma mirror` 仍用于提交前左移验证。
- 它不再是 `main` 的 required check，也不再作为独立 merge gate。
- 它必须继续复用：
  - `APP_ENV=gamma` / `APP_RUNTIME_ENV=gamma`
  - `app_gamma_seed_manifest.json`
  - `deploy/shared/gamma_validation_suites.json`
  - 共享的 chat-avatar / gamma patrol 设备旅程脚本与证据字段

## 5. 依赖与前置

### 5.1 GitHub Secrets / Variables

| 名称 | 用途 |
|------|------|
| `GAMMA_ECS_PASSWORD` 或 `GAMMA_ECS_SSH_KEY` | ECS gamma 部署认证（`04` / `08` 必需其一） |
| `GAMMA_TEST_AUTH_TOKEN` | gamma hosted/self-hosted 鉴权 |
| `vars.GAMMA_ECS_HOST` / `vars.GAMMA_ECS_PUBLIC_HOST` | ECS 主机与公网入口 |
| `vars.GAMMA_BASE_URL` / `vars.GAMMA_PRODUCT_OPS_BASE_URL` | 可选 URL 覆盖 |
| `vars.MEDIA_AVATAR_CDN_BASE_URL` | chat-avatar 媒体基址 |

完整矩阵见 [environment_matrix.md](environment_matrix.md)。

### 5.2 Self-hosted Runner

- 统一使用当前开发机注册的 `self-hosted` + `macOS` runner。
- 设备发现通过 `flutter devices --machine` 动态完成。
- `04` / `05` 都要求 Android 与 iOS 两个平台都有可见设备，并且全部通过。
- artifact 必须包含设备清单、原始日志、命令清单与截图/失败截图。

## 6. 验证清单

1. `main` 分支保护中 required checks 配置为 `03`、`04`、`05`。
2. `04` 成功执行 ECS gamma hosted pre 链。
3. `04` 的 gamma Android / iOS assistant、chat-avatar 自托管矩阵全部成功。
4. `05` 的 alpha / beta Android / iOS 自托管矩阵全部成功。
5. `04` / `05` 的 summary 下载 artifact 并完成证据校验。
6. `08` 仅在需要手动 onebox / prod 复验时使用。

## 7. 参考

- `deploy/shared/environment_matrix.md`
- `deploy/shared/branch_strategy.md`
- `deploy/shared/deliver_to_production_runbook.md`
- `deploy/shared/workflow_consolidation_plan.md`
- `.github/workflows/pre-release-gate.yml`
- `.github/workflows/app-env-device-matrix-self-hosted.yml`
- `.github/workflows/gamma-ecs-pre-hosted-core.yml`
- `deploy/shared/gamma_validation_suites.json`
