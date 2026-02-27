---
name: /opsx-prune
id: opsx-prune
category: Workflow
description: 检测并清理特性树中的过期/作废节点（Stale Node Detection & Cleanup）
---

> 主线：`specs/00_MASTER_DEVELOPMENT_FLOW.md`
> 节点生命周期标准：`specs/feature-tree/00_FEATURE_TREE_STANDARD.md` §四

**核心职责**：在 deliver/apply 完成后，或定期复盘时，扫描特性树中已过期、被取消或
被替代的节点，给出清理建议，并按用户确认执行标记或删除操作。

---

## 两种执行模式

| 模式 | 触发方式 | 行为 |
|------|----------|------|
| **scan**（默认）| `/opsx-prune` | 扫描全树，输出过期节点报告，不做任何修改 |
| **cancel** | `/opsx-prune cancel <node-path>` | 将指定节点标记为 `cancelled` |
| **deprecate** | `/opsx-prune deprecate <node-path> --superseded-by <new-path>` | 将节点标记为 `deprecated`，写入替代节点路径 |
| **delete** | `/opsx-prune delete <node-path>` | 删除节点目录（需二次确认），更新 tree_index |

---

## 步骤

### 步骤 1：扫描过期节点

从 `specs/feature-tree/tree_index.yaml` 读取全树，逐节点检测以下过期条件：

#### 1A. 孤儿目录（Orphan Directory）
条件：目录存在于 `specs/feature-tree/` 但不在 `tree_index.yaml` 中。
严重度：BLOCKING（`gate.sh` 也会检测）。

#### 1B. 僵尸引用（Zombie Reference）
条件：`tree_index.yaml` 中引用的 `path` 目录不存在（且 `status ≠ planned`）。
严重度：BLOCKING（`gate.sh` 也会检测）。

#### 1C. 规划长期未推进（Long-stale Specified）
条件：`status=specified` + tasks.md 全为 `[ ]` + **最后一次 git 变更超过 90 天**。
严重度：WARNING。
建议操作：重确认优先级，或 `/opsx-prune cancel`。

#### 1D. 实施中断超期（Long-stale In-progress）
条件：`status=in_progress` + acceptance.yaml 存在 `pending` 项 + **最后一次 git 变更超过 60 天**。
严重度：WARNING。
建议操作：重启实施，或降级为 `specified`，或 `/opsx-prune cancel`。

#### 1E. 归档未回写（Archive Not Synced）
条件：所有当前交付任务均为 `[x]`，acceptance.yaml 所有 An 为 `implemented`，但 `status ≠ completed/archived`。
严重度：WARNING。
建议操作：执行 `/opsx-archive` 完成回写。

#### 1F. 需求已被替代（Superseded）
条件：spec.md 顶部已有 `> **DEPRECATED**` 标注，但 `tree_index.yaml` status 仍为 `specified/in_progress`。
严重度：WARNING。
建议操作：`/opsx-prune deprecate`。

#### 1G. 取消后残留任务（Cancelled with Open Tasks）
条件：`status=cancelled` 但 tasks.md 中仍有 `[ ]` 任务。
严重度：WARNING（`gate.sh` 也会检测）。
建议操作：清理 tasks.md 中残余任务。

---

### 步骤 2：输出过期节点扫描报告

```
过期节点扫描报告（/opsx-prune scan）

━━━ BLOCKING（需修复，影响 gate） ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[1B] 僵尸引用（tree_index 路径不存在）：
  → runtime/runtime-client-foundation/old-removed-module
    修复：/opsx-prune delete runtime/runtime-client-foundation/old-removed-module
          或手动从 tree_index.yaml 中删除该条目

━━━ WARNING（建议处理，不阻塞 gate） ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[1C] 规划长期未推进（>90天，全 [ ] tasks）：
  → assistant-run-learning/learning-event-feedback-injection
    最后变更：2025-11-15 （111 天前）
    处理选项：
      a) 重确认优先级 → /opsx-ff update assistant-run-learning/...
      b) 取消 → /opsx-prune cancel assistant-run-learning/...
      c) 延期保留 → /opsx-prune defer assistant-run-learning/... --until Q3-2026

[1E] 归档未回写：
  → discovery-content/content-display-journey-consistency/feed-item-dto-contract
    所有 [x] 完成，但 status 仍为 in_progress
    修复：/opsx-archive discovery-content/content-display-journey-consistency/feed-item-dto-contract

━━━ 统计 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BLOCKING:  N 项（执行 make gate 可查看详情）
WARNING:   N 项

建议执行顺序：
  1. 先修复 BLOCKING 项（gate.sh 拦截）
  2. 再处理 WARNING 项（复盘建议）
```

---

### 步骤 3（cancel 模式）：标记节点为 cancelled

执行 `/opsx-prune cancel <node-path>` 时：

1. 确认节点路径存在于 `tree_index.yaml`
2. 在 `spec.md` 顶部插入取消标注：
   ```markdown
   > **CANCELLED**: <日期> — <取消原因（从用户输入获取）>
   ```
3. 将 `tasks.md` 中 `[ ]` 任务行改为 `~~- [ ]~~`（strikethrough）
4. 更新 `tree_index.yaml` 中节点及其所有子节点的 `status: cancelled`
5. 输出：
   ```
   已取消：<node-path>
   ├─ spec.md 顶部已加注 CANCELLED 标注
   ├─ tasks.md 中 N 个未完成任务已标记删除线
   └─ tree_index.yaml status → cancelled（含 N 个子节点）
   ```

---

### 步骤 4（deprecate 模式）：标记节点为 deprecated

执行 `/opsx-prune deprecate <node-path> --superseded-by <new-path>` 时：

1. 确认 `<new-path>` 节点存在
2. 在 `spec.md` 顶部插入废弃标注：
   ```markdown
   > **DEPRECATED**: <日期> — 已由 `<new-path>` 取代
   ```
3. 在 `acceptance.yaml` 顶层加入：
   ```yaml
   superseded_by: <new-path>
   ```
4. 更新 `tree_index.yaml` 中节点 `status: deprecated`
5. 输出废弃摘要

---

### 步骤 5（delete 模式）：删除节点目录

执行 `/opsx-prune delete <node-path>` 时（**危险操作，需二次确认**）：

```
危险操作确认：
将永久删除目录：specs/feature-tree/<node-path>/
包含文件数：N 个
确认删除？[yes/NO]
```

确认后：
1. 删除目录（`rm -rf specs/feature-tree/<node-path>/`）
2. 从 `tree_index.yaml` 中移除该节点条目及所有子节点条目
3. 输出：已删除目录 + 从 tree_index 移除 N 个条目

---

## 过期检测快捷方式

在 `/opsx-verify` 和 `/opsx-archive` 执行完成后，自动触发一次轻量过期扫描：
- 只检测 1E（归档未回写），BLOCKING
- 只检测 1B（僵尸引用），BLOCKING
- 其他 WARNING 项仅在 `/opsx-prune scan` 时全量扫描

---

## 与其他命令的关系

| 命令 | 触发时机 |
|------|----------|
| `/opsx-ff` update | 更新节点时若父节点已 `cancelled/deprecated`，警告用户 |
| `/opsx-archive` | 归档后自动标记 `status: completed` + `archived: true`；触发轻量过期扫描 |
| `/opsx-verify` | 漂移报告后触发轻量过期扫描（1B + 1E） |
| `/opsx-prune scan` | 手动触发全量过期扫描 |
| `make gate` / `make gate-full` | 自动检测 BLOCKING 项（孤儿目录、僵尸引用、lifecycle 一致性） |
