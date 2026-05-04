# 分支策略

> 与 `deliver_to_production_runbook.md`、`ci_cd_end_to_end_design.md` 对齐。当前策略已取消“定时 dev1.0 → main 自动合并”，统一改为**用户显式发起 PR / merge queue 合流**。

---

## 1. 策略概要

| 分支 / 模式 | 用途 | 合入方式 |
|------|------|----------|
| **dev1.0** | 分支开发模式下的日常集成分支 | 功能分支先合到 `dev1.0`，再由用户显式发起 `dev1.0 -> main` PR |
| **main** | 发布主干 | 仅通过 PR + **merge queue** 更新；阻断项为 `03` / `04` / `05` |
| **trunk development** | 无长期集成分支的直接主干开发模式 | 功能分支直接对 `main` 发起 PR，同样进入 merge queue |

- **模式 A：分支开发**：功能分支先合到 `dev1.0`，由用户在需要发布时显式发起 `dev1.0 -> main` PR。
- **模式 B：主干开发**：功能分支直接对 `main` 发 PR，不经过 `dev1.0`。
- **统一门禁**：无论采用哪种模式，进入 `main` 前都必须经过 **merge queue**，并跑通：
  - `03. Delivery Gate`
  - `04. Pre-Release Gate`
  - `05. App Env Device Matrix`
- **已移除**：任何定时 merge、自动把 `dev1.0` 推进到 `main` 的 workflow / 脚本。

---

## 2. 本地开发约定

- 分支开发模式下，日常提交仍以 **`dev1.0`** 为默认集成目标。
- `main` 仅作为发布主干，不接受 direct push。
- 本地提交前必须先通过 `make gate-local-gamma`。
- 进入 `main` 的动作必须由用户显式发起 PR，并由 merge queue 放行；禁止保留第二条“脚本等绿后自动 merge”路径。

---

## 3. 合流流程

### 3.1 分支开发（`dev1.0`）

```text
feature branch
  → PR 合并到 dev1.0
  → 用户显式发起 dev1.0 -> main PR
  → merge queue 运行 03 / 04 / 05
  → 全绿后进入 main
  → main 上再跑 02 / 07（post-main）
```

### 3.2 主干开发（trunk）

```text
feature branch
  → 用户显式发起 feature -> main PR
  → merge queue 运行 03 / 04 / 05
  → 全绿后进入 main
  → main 上再跑 02 / 07（post-main）
```

---

## 4. GitHub 分支保护建议

| 分支 | 建议配置 |
|------|----------|
| **main** | 禁止 direct push；启用 merge queue；required checks 至少包含 `03. Delivery Gate`、`04. Pre-Release Gate`、`05. App Env Device Matrix` |
| **dev1.0** | 作为分支开发集成分支时，可要求 PR；是否强制检查由团队节奏决定，但不得再依赖定时合并到 `main` |

---

## 5. 参考

- `deploy/shared/deliver_to_production_runbook.md` — 端到端 runbook
- `deploy/shared/ci_cd_end_to_end_design.md` — CI/CD 闭环
- `deploy/shared/workflow_consolidation_plan.md` — 01~08 工作流职责划分
