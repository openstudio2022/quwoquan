---
name: /commit
id: commit
category: Workflow
description: 提交已完成的 Scenario slice 与对应 CR（推送到 dev1.0 后以远端 CI 绿灯为合入完成判据）
---

> SDD 主流程：... → dev（已归档） → **commit** → deploy

`/commit` 的前置对象是：**已完成的 `L3_scenario` slice 与其对应 CR 范围**。

## 前置条件

- 四件套齐全
- `plan.yaml` 的目标 slice 已完成
- `acceptance.yaml` 无 `pending`
- `tests` 证据已回填
- `CR` 已完成本轮修订

## 提交前门禁

```bash
make gate-local-gamma
```

`make gate-local-gamma` 是后续所有 commit 的默认准入，必须在本地完成 `T1 -> T4` 左移覆盖并生成 `artifacts/local-gamma/report.json`：

- `T1`：metadata、拓扑、环境包、seed manifest、错误码、静态语义与生成物校验。
- `T2`：Flutter/Go/Ops 模块、Widget、Provider/Journey 测试。
- `T3`：本地 gamma mirror 的真实 API、真实存储副作用、错误响应与 RemoteRepository smoke。
- `T4`：至少一台模拟器或真机的 Patrol 核心旅程。

本地 DNS/TLS、设备、服务依赖或 seed/reset 能力不足时，状态必须为 `GATE_BLOCK`，不得降级为通过或只用 `make gate` 替代。

必要时按变更范围补充：

- Flutter tests
- `make verify-app-mock-isolation`（`quwoquan_app` 内 Mock/Remote、UI/Core import、`main_prod` 或构建脚本变更时）
- `make verify-app-lib-test-only-symbols`（`lib/**` 新增 `createForTest` / 测试工厂时）
- service gate

## 提交行为（默认先 dev1.0；进入 main 以 merge queue 绿灯为准）

1. 确认当前分支为日常开发分支 **`dev1.0`**（与 `deploy/shared/branch_strategy.md` 一致；禁止绕过策略直推 `main`）。
2. `git status` → `git add` → `git commit`
3. `git push origin dev1.0`
4. 若团队仍使用 `dev1.0` 作为日常集成分支，可按需等待该分支上的远端校验通过，再决定是否发起进入 `main` 的 PR。
5. **进入 `main` 的成功判据** 不再是分支上的单个 workflow，而是 **merge queue** 对 `03. Delivery Gate`、`04. Pre-Release Gate`、`05. App Env Device Matrix` 的 required checks 全绿。

## 合入主干（main）与后续 CI

- **合入 `main`**：由用户显式发起 PR（`dev1.0 -> main` 或 feature branch -> `main`），并进入仓库的 **merge queue**。
- **merge queue 阻断项**：`03. Delivery Gate`、`04. Pre-Release Gate`、`05. App Env Device Matrix`。
- **合入 `main` 之后**：`push main` 会触发 **`02. Service Pipeline`** 与 **`07. Deploy To Prod (Auto)`**；手动的发布 / onebox 演练分别使用 **`06`**、**`08`**。

## 输出

```text
提交并完成远端校验：<feature-path>
L3_scenario: <scenario>
CR: <change-request>
main merge queue checks: PASS（03 / 04 / 05）
下一步：跟踪 main 上的 02 / 07，必要时执行 06 / 08
```
