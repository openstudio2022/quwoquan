# daily-merge-release-strategy 设计

## 设计动因

当前 deliver 入库直接到 main，pre-release 由 v*-rc* tag 手动触发。需求：日常代码仅合入 dev1.0，每日固定时间（如 6:00）自动 merge 至 main，merge 后自动触发 deploy integration 与 prod 首阶段，形成可预测的日节奏发布。

## 适用场景与约束

- **适用**：日节奏发布、自动化 deploy 到 integration 与 prod  Stage 1
- **约束**：GitHub Actions 需 merge 权限（GITHUB_TOKEN 或 PAT）；pre-release-gate 需支持 merge 场景的版本号来源
- **局限性**：scheduled workflow 依赖 GitHub runner 可用；merge 冲突需人工介入

## 业界对标与多方案对比

### 1. 定时 merge 实现方式

| 方案 | 职责 | 优点 | 缺点 | 选型 |
|------|------|------|------|------|
| **A：GitHub Actions scheduled + gh CLI merge** | workflow 内执行 `gh pr create` + merge | 可复用现有 Actions；审计清晰 | 需 PR；可能无变更时产生空 PR | 备选 |
| **B：GitHub Actions scheduled + git merge** | workflow 内 checkout、merge、push | 直接 merge，无 PR 开销 | 需 PAT 写权限；冲突时 fail | ✓ 选定 |
| **C：外部 cron（如 Jenkins/自建）** | 外部系统定时调用 GitHub API | 可控、可加审批 | 需额外基础设施 | 不选 |

**选型**：B — 在 workflow 内用 `git merge origin/dev1.0` 并 push 到 main。冲突时 workflow 失败，通知人工处理。

### 2. pre-release 触发方式（merge 后如何触发 deploy）

| 方案 | 方式 | 优点 | 缺点 | 选型 |
|------|------|------|------|------|
| **A：pre-release-gate 增加 push to main** | `on.push.branches: [main]` | merge 即触发，简单 | 需为 merge 场景约定版本号（如 vYYYY.MM.DD-daily） | ✓ 选定 |
| **B：merge workflow 内 workflow_call pre-release** | merge 完成后 call 04 | 流程集中 | 需修改 pre-release-gate 支持 reusable；版本号同样需约定 | 备选 |

**选型**：A — pre-release-gate 增加 `on.push.branches: [main]`，与 tag 触发并存；merge 场景下从 commit SHA 或日期生成版本号注入 kustomize。

### 3. 版本号约定（merge 场景）

| 方案 | 格式 | 说明 |
|------|------|------|
| **日期版本** | vYYYY.MM.DD.daily 或 vYYYY.MM.DD.HHMM | 与 tag v*-rc* 区分；kustomize replacement 可注入 |
| **commit SHA** | short SHA 作为 IMAGE_VERSION | 与现有 tag 解析逻辑兼容，需扩展 |

**选型**：采用 `vYYYY.MM.DD-daily` 或 `vYYYY.MM.DD.0` 作为 merge 日版本，在 pre-release-gate push 触发时由 workflow 生成并注入。

## 关键决策

### 1. 流程串联

```
dev1.0 日常 PR
  → delivery-gate（L1+L2）✓ 已有
  → merge 定时 6:00（UTC 22:00 ≈ CST 6:00）
  → merge-dev1.0-to-main workflow: git merge dev1.0 → main, push
  → push to main 触发 pre-release-gate（新增 on.push）
  → gate → deploy-integration → L3 → L4
  → deploy-prod-auto Stage 1（workflow_run 已有）
```

### 2. merge workflow 设计要点

- **cron**：`0 22 * * *`（UTC 22:00 ≈ Asia/Shanghai 6:00），可配置
- **前置**：可加 `dev1.0 领先 main` 判断，避免无变更时产生空 merge
- **冲突**：merge 冲突时 fail，通知（issue/ Slack/钉钉）

### 3. 分支保护建议

- main：禁止 direct push，仅允许通过 merge；PR 默认 base 为 dev1.0 时，需策略文档约定
- dev1.0：PR 需通过 delivery-gate

## 未来演进

- **审批门控**：merge 前可选「需 N 人 approve」或 Environment protection
- **多时区**：cron 支持按团队时区配置
- **回滚**：merge 后若 pre-release 失败，可增加「回滚 main 到 merge 前」的可选步骤
