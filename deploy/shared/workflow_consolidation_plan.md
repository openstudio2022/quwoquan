# Workflow 整合方案

> 原则：gate 按阶段命名；`03` 只负责 L1/L2；`04` 收口为 ECS gamma 主门禁；`05` 收口为本地 self-hosted alpha/beta 设备矩阵；`08` 只保留手动发布与复验。
>
> **特性树**：`specs/feature-tree/runtime/deliver-deploy-prod-pipeline/workflow-naming-consolidation/`

## 1. 分层与职责

| 层级 | 依赖 | 执行时机 |
|------|------|----------|
| **L1** | 无（Mock） | `03. Delivery Gate` |
| **L2** | MongoDB、Redis（testcontainers） | `03. Delivery Gate` |
| **Gamma hosted checks** | ECS pre 部署后的公网 gamma | `04. Pre-Release Gate` |
| **Gamma self-hosted checks** | 本地 Mac + Android/iOS 设备 + ECS gamma | `04. Pre-Release Gate` |
| **Alpha/Beta self-hosted checks** | 本地 Mac + Android/iOS 设备 + alpha/beta endpoint | `05. App Env Device Matrix` |

## 2. Workflow 命名规范（序号 + 首字母大写）

| 序号 | Workflow | 环境 | 说明 |
|------|----------|------|------|
| 01 | App Pipeline | Release / Manual | 端侧发布构建：`v*` tag / 手动 macOS 构建 |
| 02 | Service Pipeline | Main Branch | main 后云侧构建：Go build、Python 镜像、prod 校验 |
| 03 | Delivery Gate | PR Rule | PR 主门禁：拓扑 + L1 + L2 |
| 04 | Pre-Release Gate | PR Rule / ECS Gamma | ECS gamma hosted pre 链 + 本地 gamma Android/iOS assistant/avatar 旅程 |
| 05 | App Env Device Matrix | PR Rule / Self-hosted | 本地 self-hosted alpha/beta Android/iOS 设备矩阵唯一入口 |
| 06 | Deploy To Prod (Gray) | Production — Gray | 半自动 `workflow_dispatch` |
| 07 | Deploy To Prod (Auto) | Production — Full | main 后自动推进 |
| 08 | Deploy Gamma ECS | Gamma / Onebox | 手动 ECS gamma 发布与 prod 复验 |

## 3. 去重决策

- **03 vs 04**：`03` 不再重复任何部署动作；`04` 不再重复 L1/L2。
- **04 vs 08**：二者复用同一条 `gamma-ecs-pre-hosted-core.yml` hosted 预部署链；`04` 是 PR required check，`08` 是手动 wrapper。
- **05 vs 04**：`05` 只负责 alpha/beta 本地矩阵；`04` 只负责 gamma assistant/avatar 本地矩阵。
- **local-gamma mirror**：保留为提交前左移预测试，不再作为 `main` required check，也不再单独表达成 merge gate。

## 4. 主门禁拓扑

```text
pull request -> main
├── 03. Delivery Gate
│   ├── topology
│   ├── service L2
│   └── app L1
├── 05. App Env Device Matrix
│   ├── discover alpha/beta devices
│   ├── alpha / Android+iOS
│   └── beta / Android+iOS
└── 04. Pre-Release Gate
    ├── ECS gamma hosted pre core
    │   ├── package bundle
    │   ├── deploy ECS pre
    │   ├── assistant gamma smoke
    │   ├── gamma API contract
    │   └── chat avatar API probe
    └── self-hosted gamma Android+iOS
        ├── assistant matrix
        └── chat avatar matrix

push main
├── 02. Service Pipeline
└── 07. Deploy To Prod (Auto)
```

## 5. 当前收口规则

- `04` / `05` 都要求本地 Mac 上 **Android 与 iOS 都存在且都通过**；不再接受“只有一类设备可见也算通过”的口径。
- self-hosted 设备矩阵必须上传可审计 artifact：设备清单、原始日志、命令清单、截图/失败截图。
- summary job 不只看 exit code，还会下载 artifact 并校验证据文件是否真实存在。
- gamma 旅程以 `deploy/shared/gamma_validation_suites.json` 为单源；当前基线是 `assistant_main_chain` 与 `chat_avatar_sync`，后续按业务对象继续补齐。

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
