# daily-merge-release-strategy 设计

## 设计动因

旧方案依赖每日定时把 `dev1.0` 自动 merge 到 `main`，存在等待不可控、重复重跑和职责分散的问题。现改为：用户显式发起 PR，所有进入 `main` 的代码统一经过分支保护 required checks 阻断。

## 适用场景与约束

- **适用**：分支开发与 trunk development 并存的主干治理
- **约束**：需要 GitHub branch protection；self-hosted runner 需在线，且 `04/05` 需要同时发现 Android 与 iOS 设备
- **局限性**：ECS gamma / self-hosted 设备验证会成为进入 `main` 的真实阻断成本

## 业界对标与多方案对比

### 1. main 合流实现方式

| 方案 | 职责 | 优点 | 缺点 | 选型 |
|------|------|------|------|------|
| **A：定时 workflow 自动 merge** | cron + git merge / gh merge | 自动化强 | 非显式、排队和冲突不可控、会产生重复重跑 | 不选 |
| **B：显式 PR + required checks** | 用户创建 PR，GitHub 分支保护规则跑 required checks | 路径清晰、阻断可见、与 trunk/dev1.0 模式统一 | 需配置 required checks | ✓ 选定 |
| **C：人工本地 merge 再 push main** | 本地 merge 后直推 | 简单 | 绕过主干阻断，风险高 | 不选 |

**选型**：B — 统一采用显式 PR + required checks，不再保留任何定时自动 merge。

### 2. 主干前后 workflow 边界

| 方案 | 方式 | 优点 | 缺点 | 选型 |
|------|------|------|------|------|
| **A：重验证放在 push main** | 所有重检查在 `main` 后再跑 | 实现简单 | 失败已进入 `main`，且重复耗时 | 不选 |
| **B：重验证前移到 PR required checks** | `03/04/05` 只在 `pull_request(main)` / 手动执行 | 先验阻断、避免 main 后重跑 | merge 前成本上升 | ✓ 选定 |

**选型**：B — `03/04/05` 前移到 `pull_request(main)`；`02/07` 保留 main 后动作；`06/08` 为手动。

### 3. 设备矩阵入口

- 旧的 `05` wrapper + `05b` self-hosted 双入口会造成 UI 重复与职责不清。
- 新方案保留 `app-env-device-matrix-self-hosted.yml` 作为唯一 **`05. App Env Device Matrix`**：
  - `pull_request(main)`：主干阻断
  - `workflow_call`：供 `08` 等复用
  - `workflow_dispatch`：手动调试

## 关键决策

### 1. 流程串联

```text
feature / dev1.0
  → 用户显式发起 PR 到 main
  → PR required checks
      ├─ 03 Delivery Gate
      ├─ 05 App Env Device Matrix
      └─ 04 Pre-Release Gate
  → 通过后进入 main
  → push main
      ├─ 02 Service Pipeline
      └─ 07 Deploy To Prod (Auto)
```

### 2. PR 规则设计要点

- `main` required checks：`03`、`04`、`05`
- `03/04/05` 不再响应分支 push，避免重复耗时
- self-hosted 设备矩阵对 `main` required checks 要求当前 Mac 同时具备可见 Android 与 iOS 设备

### 3. 分支保护建议

- `main`：禁止 direct push，仅允许通过 PR + required checks
- `dev1.0`：是否要求 PR 由团队决定，但不得再依赖定时自动推进到 `main`

## 未来演进

- **审批门控**：PR 合入前可补充 approve / CODEOWNERS
- **更细粒度 paths 优化**：未来可为 `03/04/05` 增加 changed-files 感知，进一步缩短队列时长
- **回滚**：若 `main` 后 `02/07` 失败，可配套发布回滚 runbook
