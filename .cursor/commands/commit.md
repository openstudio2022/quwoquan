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

## 提交行为（必须先 dev1.0，且以远端绿灯为「合入成功」）

1. 确认当前分支为日常开发分支 **`dev1.0`**（与 `deploy/shared/branch_strategy.md` 一致；禁止绕过策略直推 `main`）。
2. `git status` → `git add` → `git commit`
3. `git push origin dev1.0`
4. **必须等待** 远端 **`03. Delivery Gate`**（`.github/workflows/delivery-gate.yml`）对**本次推送所对应 commit** 执行完成且 **conclusion 为 success**。未绿则**不视为合入成功**，应本地修复后重复 2～4，直到变绿。

### 等待 Delivery Gate 变绿（本地）

依赖：[GitHub CLI](https://cli.github.com/) `gh` 且已 `gh auth login`，或提供 `GITHUB_TOKEN`（`repo` 读权限即可）。

```bash
# 在仓库根目录；默认最多等待 1 小时（轮询间隔约 25s）
bash scripts/gh_wait_delivery_gate_green.sh dev1.0 3600
```

等价（仅 Python，需 `GITHUB_REPOSITORY` + `GITHUB_TOKEN`）：

```bash
export GITHUB_REPOSITORY="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
export GITHUB_TOKEN="$(gh auth token)"
python3 scripts/ci_assert_delivery_gate_green_for_branch.py dev1.0 --wait-seconds 3600 --poll-interval 25
```

说明：脚本会对比 **dev1.0 当前 HEAD commit** 与 Delivery Gate run 的 `head_sha`，避免「旧 run 已成功、新 push 尚未跑完」的误判。

## 合入主干（main）与后续 CI

- **合入 `main`**：由仓库策略 **定时** workflow `07. Merge dev1.0 To Main`（`.github/workflows/merge-dev1.0-to-main.yml`）在 **断言 dev1.0 上 Delivery Gate 已绿** 后再执行 merge；亦可 **手动** `workflow_dispatch` 同一 workflow（仍会先断言再 merge）。
- **合入 `main` 之后**：推送会触发 **`04. Pre-Release Gate`**，其中包含 **助手 alpha / gamma runtime 冒烟**（`APP_RUNTIME_ENV=alpha` mock 与 `gamma` remote+`CLOUD_GATEWAY_BASE_URL`），以及既有 G5a / L3 / L4 等。**该 workflow 全部成功**才视为发布前链路通过；任一步失败须修复后重新走 push（或重新 merge 触发），直至全绿。

## 输出

```text
提交并完成远端校验：<feature-path>
L3_scenario: <scenario>
CR: <change-request>
dev1.0 Delivery Gate: PASS（已对应当前 HEAD）
下一步：等待定时 merge → main；再跟 /deploy 与 pre-release 全绿
```
