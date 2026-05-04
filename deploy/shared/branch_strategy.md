# 分支策略

> 与 `deliver_to_production_runbook.md`、`ci_cd_end_to_end_design.md` 对齐。当前策略只有一条主干入口：**用户显式发起 PR，且通过 `main` 的 required checks 后才能合入**。

## 1. 策略概要

| 分支 / 模式 | 用途 | 合入方式 |
|------|------|----------|
| **dev1.0** | 分支开发模式下的日常集成分支 | 功能分支先合到 `dev1.0`，再由用户显式发起 `dev1.0 -> main` PR |
| **main** | 发布主干 | 仅通过 PR 更新；阻断项固定为 `03` / `04` / `05` |
| **trunk development** | 无长期集成分支的直接主干开发模式 | 功能分支直接对 `main` 发起 PR，同样受 required checks 保护 |

- **模式 A：分支开发**：功能分支先合到 `dev1.0`，需要发布时再显式发起 `dev1.0 -> main` PR。
- **模式 B：主干开发**：功能分支直接对 `main` 发 PR，不经过 `dev1.0`。
- **统一门禁**：无论采用哪种模式，进入 `main` 前都必须通过：
  - `03. Delivery Gate`：L1/L2、静态质量门。
  - `04. Pre-Release Gate`：ECS gamma hosted pre 链 + 本地 self-hosted gamma Android/iOS assistant/avatar 旅程。
  - `05. App Env Device Matrix`：本地 self-hosted alpha/beta Android/iOS 设备矩阵与证据校验。
- **已移除**：任何定时 merge、自动把 `dev1.0` 推进到 `main` 的 workflow / 脚本。

## 2. 本地开发约定

- 分支开发模式下，日常提交仍以 `dev1.0` 为默认集成目标。
- `main` 只作为发布主干，不接受 direct push。
- 本地提交前仍建议执行 `make gate-local-gamma`，但它是**左移预测试**，不是 `main` 的 required check。
- `local-gamma mirror` 与云侧 gamma 共用 `APP_ENV=gamma` / `APP_RUNTIME_ENV=gamma`、同一份 seed 语义与 `deploy/shared/gamma_validation_suites.json`；它负责提交前自检，不再作为独立 merge gate。

## 3. 合流流程

### 3.1 分支开发（`dev1.0`）

```text
feature branch
  → PR 合并到 dev1.0
  → 用户显式发起 dev1.0 -> main PR
  → PR required checks 运行 03 / 04 / 05
  → 全绿后进入 main
  → main 上再跑 02 / 07（post-main）
```

### 3.2 主干开发（trunk）

```text
feature branch
  → 用户显式发起 feature -> main PR
  → PR required checks 运行 03 / 04 / 05
  → 全绿后进入 main
  → main 上再跑 02 / 07（post-main）
```

## 4. GitHub 分支保护建议

| 分支 | 建议配置 |
|------|----------|
| **main** | 禁止 direct push；要求通过 Pull Request 合并；required checks 至少包含 `03. Delivery Gate`、`04. Pre-Release Gate`、`05. App Env Device Matrix` |
| **dev1.0** | 作为分支开发集成分支时，可要求 PR；是否强制检查由团队节奏决定，但不得再依赖任何自动合流到 `main` 的路径 |

## 5. 参考

- `deploy/shared/deliver_to_production_runbook.md`
- `deploy/shared/ci_cd_end_to_end_design.md`
- `deploy/shared/workflow_consolidation_plan.md`
- `deploy/shared/gamma_validation_suites.json`
