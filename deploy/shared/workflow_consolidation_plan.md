# Workflow 整合方案

> 原则：gate 按阶段命名；`03` 只负责 L1/L2；`04` 收口为 PR 轻量 gamma preflight（readiness 阻断、smoke 告警）；`05` 收口为本地 self-hosted 设备矩阵（按 profile 分层）；`08` 手动完整 ECS 部署与复验；`09` nightly/手动全量验证。
>
> **特性树**：`specs/feature-tree/runtime/deliver-deploy-prod-pipeline/workflow-naming-consolidation/`

## 1. 分层与职责

| 层级 | 依赖 | 执行时机 |
|------|------|----------|
| **L1** | 无（Mock） | `03. Delivery Gate` |
| **L2** | MongoDB、Redis（testcontainers） | `03. Delivery Gate` |
| **Gamma readiness probe** | 已运行的共享 gamma | `04. Pre-Release Gate`（pr_light 默认） |
| **Gamma full ECS deploy + checks** | ECS pre 部署后的公网 gamma | `08. Deploy Gamma ECS`（手动）/ `09. Gamma Full Validation`（nightly） |
| **Alpha/Beta self-hosted checks** | 本地 Mac + Android/iOS 设备 + alpha/beta endpoint | `05. App Env Device Matrix`（pr_light） |
| **Gamma self-hosted checks** | 本地 Mac + Android/iOS 设备 + ECS gamma | `09. Gamma Full Validation`（nightly_full） |

## 2. Workflow 命名规范（序号 + 首字母大写）

| 序号 | Workflow | 环境 | 说明 |
|------|----------|------|------|
| 01 | App Pipeline | Release / Manual | 端侧发布构建：`v*` tag / 手动 macOS 构建 |
| 02 | Service Pipeline | Main Branch | main 后云侧构建：Go build、Python 镜像、prod 校验 |
| 03 | Delivery Gate | PR Rule | PR 主门禁：拓扑 + L1 + L2 |
| 04 | Pre-Release Gate | PR Rule / Gamma Probe | PR 轻量 gamma preflight（readiness 阻断 + smoke 漂移告警）；显式 manual_full 触发完整 ECS 链 |
| 05 | App Env Device Matrix | PR Rule / Self-hosted | 本地 self-hosted 设备矩阵（pr_light: alpha/beta；nightly_full: 全环境全平台） |
| 06 | Deploy To Prod (Gray) | Production — Gray | 半自动 `workflow_dispatch` |
| 07 | Deploy To Prod (Auto) | Production — Full | main 后自动推进 |
| 08 | Deploy Gamma ECS | Gamma / Onebox | 手动完整 ECS gamma 部署、验证与 prod 复验 |
| 09 | Gamma Full Validation | Nightly / Manual | 每晚 22:00 UTC+8 全量：ECS deploy + full semantic + Patrol UI + 全设备矩阵 |

## 3. 去重决策

- **03 vs 04**：`03` 不再重复任何部署动作；`04` 不再重复 L1/L2。
- **04 vs 08/09**：`04` PR 默认只做轻量探针（不部署 gamma）；`08`/`09` 负责完整 ECS 部署与深度验证。三者不再重复同一条完整部署链。
- **05 按 profile 分层**：PR 默认 `pr_light`（alpha/beta），nightly 调用时传 `nightly_full`（全环境全平台）。
- **local-gamma mirror**：保留为提交前左移预测试，不再作为 `main` required check，也不再单独表达成 merge gate。

## 4. 主门禁拓扑

```text
pull request -> main (pr_light profile)
├── 03. Delivery Gate
│   ├── topology
│   ├── service L2
│   └── app L1
├── 05. App Env Device Matrix (pr_light: alpha/beta, allow_missing)
│   ├── discover devices
│   ├── alpha / Android+iOS
│   └── beta / Android+iOS
└── 04. Pre-Release Gate (pr_light: probe shared gamma, no deploy)
    ├── gamma readiness (blocking)
    ├── assistant protocol smoke (warning only)
    └── chat avatar API probe (warning only)

push main
├── 02. Service Pipeline
└── 07. Deploy To Prod (Auto)

nightly 22:00 UTC+8 (nightly_full profile)
└── 09. Gamma Full Validation
    ├── ECS gamma hosted pre core (full_semantic)
    │   ├── package bundle
    │   ├── deploy ECS pre
    │   ├── readiness gate
    │   ├── T3 API contract
    │   ├── assistant full semantic smoke
    │   └── chat avatar API probe
    ├── Patrol full UI profile
    ├── gamma assistant device matrix (nightly_full)
    └── gamma chat-avatar device matrix (nightly_full)

manual (08 - manual_full profile)
└── 08. Deploy Gamma ECS
    ├── preflight (verify 03/04/05 passed)
    ├── ECS gamma hosted pre core
    ├── ECS prod upgrade
    └── post-prod self-hosted device matrix (manual_full)
```

## 5. 当前收口规则

- **Profile 统一**：所有门禁按 `deploy/shared/gamma_validation_suites.json` 中的 profile 执行，不再各自硬编码行为。
- **PR 默认 `pr_light`**：04 只探针共享 gamma readiness（阻断）；05 只跑 alpha/beta（allow_missing）；不部署、不跑全量。
- **显式 `manual_full`/`nightly_full`**：需要完整验证时显式触发或由 nightly cron 驱动。
- **全平台强制仅在 nightly/release**：`nightly_full` 和 `release_candidate` profile 要求全平台通过；PR 允许缺席平台跳过。
- self-hosted 设备矩阵必须上传可审计 artifact：设备清单、原始日志、命令清单、截图/失败截图。
- gamma 旅程以 `deploy/shared/gamma_validation_suites.json` 为单源；当前基线是 `assistant_main_chain` 与 `chat_avatar_sync`，后续按业务对象继续补齐。
- 门禁脚本 `verify_gamma_validation_profiles.py` 和 `verify_ci_profile_consistency.py` 已串联 `make gate`。

## 6. 02/03 重复检查

| 执行内容 | 02 Service Pipeline | 03 Delivery Gate | 是否重复 |
|----------|---------------------|------------------|----------|
| Go build | ✅ `make build` | ❌ | 否 |
| Go test (L2) | ❌ | ✅ `make gate` 含 go test | 否 |
| Prod deploy 校验 | ✅ | ❌ | 否 |
| 拓扑 / metadata / 契约 | ❌ | ✅ | 否 |

**结论**：02 与 03 仍然互补；02 是 post-main 构建与 prod 清单校验，03 是 main 前质量门。

## 7. 风险与回退

- **风险**：`main` 分支 required checks 配置不完整，会出现代码进入 `main` 前未真正经过 `03/04/05`。
- **缓解**：在 `main` 分支保护中显式配置 required checks，并通过一次 `dev1.0 -> main` 验收 PR 验证。
- **回退**：可临时对 `03/04/05/08` 使用 `workflow_dispatch` 手动补跑，但不建议恢复任何定时合流模型。
