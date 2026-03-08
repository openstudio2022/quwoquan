---
name: /prune
id: prune
category: Workflow
description: 检测并清理特性树中的过期/作废节点（Stale Node Detection & Cleanup）
---

> 节点生命周期标准：`specs/feature-tree/00_FEATURE_TREE_STANDARD.md` §四

**核心职责**：在 deliver/dev 完成后，或定期复盘时，扫描特性树中已过期、被取消或被替代的节点，给出清理建议，并按用户确认执行标记或删除操作。

---

## 两种执行模式

| 模式 | 触发方式 | 行为 |
|------|----------|------|
| **scan**（默认）| `/prune` | 扫描全树，输出过期节点报告，不做任何修改 |
| **cancel** | `/prune cancel <node-path>` | 将指定节点标记为 `cancelled` |
| **deprecate** | `/prune deprecate <node-path> --superseded-by <new-path>` | 将节点标记为 `deprecated` |
| **delete** | `/prune delete <node-path>` | 删除节点目录（需二次确认），更新 tree_index |

---

## 步骤

### 步骤 1：扫描过期节点

从 `specs/feature-tree/tree_index.yaml` 读取全树，逐节点检测：

#### 1A. 孤儿目录（Orphan Directory）
条件：目录存在于 `specs/feature-tree/` 但不在 `tree_index.yaml` 中。
严重度：BLOCKING。

#### 1B. 僵尸引用（Zombie Reference）
条件：`tree_index.yaml` 中引用的 `path` 目录不存在（且 `status ≠ planned`）。
严重度：BLOCKING。

#### 1C. 规划长期未推进（Long-stale Specified）
条件：`status=specified` + tasks.md 全为 `[ ]` + 最后一次 git 变更超过 90 天。
严重度：WARNING。

#### 1D. 实施中断超期（Long-stale In-progress）
条件：`status=in_progress` + acceptance.yaml 存在 `pending` 项 + 最后一次 git 变更超过 60 天。
严重度：WARNING。

#### 1E. 归档未回写（Archive Not Synced）
条件：所有当前交付任务均为 `[x]`，acceptance.yaml 所有 An 为 `implemented`，但 `status ≠ completed/archived`。
严重度：WARNING。
处理：优先确认 `/dev` 是否已自动归档；若未回写，再执行 `/archive` 兼容补归档。

#### 1F. 需求已被替代（Superseded）
条件：spec.md 顶部已有 `> **DEPRECATED**` 标注，但 tree_index status 仍为 `specified/in_progress`。
严重度：WARNING。

#### 1G. 取消后残留任务（Cancelled with Open Tasks）
条件：`status=cancelled` 但 tasks.md 中仍有 `[ ]` 任务。
严重度：WARNING。

---

### 步骤 2：输出过期节点扫描报告

```
过期节点扫描报告（/prune scan）

━━━ BLOCKING（需修复，影响 gate） ━━━━━━━━━━━━━━━━━━━━━━━━━

[1B] 僵尸引用（tree_index 路径不存在）：
  → some/path/old-node
    修复：/prune delete some/path/old-node
          或手动从 tree_index.yaml 中删除该条目

━━━ WARNING（建议处理，不阻塞 gate） ━━━━━━━━━━━━━━━━━━━━━━━

[1C] 规划长期未推进（>90天，全 [ ] tasks）：
  → some/feature/node
    最后变更：<日期>（N 天前）
    处理选项：
      a) 重确认优先级 → /prd update some/feature/node
      b) 取消 → /prune cancel some/feature/node
      c) 延期保留 → /prune defer some/feature/node --until Q3-2026

[1E] 归档未回写：
  → some/feature/completed-but-not-archived
    所有 [x] 完成，但 status 仍为 in_progress
    修复：/archive some/feature/completed-but-not-archived

━━━ 统计 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BLOCKING:  N 项（执行 make gate 可查看详情）
WARNING:   N 项
```

---

### 步骤 3（cancel 模式）：标记节点为 cancelled

执行 `/prune cancel <node-path>` 时：

1. 在 `spec.md` 顶部插入取消标注：
   ```markdown
   > **CANCELLED**: <日期> — <取消原因>
   ```
2. 将 `tasks.md` 中 `[ ]` 任务行改为 `~~- [ ]~~`（strikethrough）
3. 更新 `tree_index.yaml` 中节点及所有子节点的 `status: cancelled`

---

### 步骤 4（deprecate 模式）：标记节点为 deprecated

执行 `/prune deprecate <node-path> --superseded-by <new-path>` 时：

1. 确认 `<new-path>` 节点存在
2. 在 `spec.md` 顶部插入废弃标注：
   ```markdown
   > **DEPRECATED**: <日期> — 已由 `<new-path>` 取代
   ```
3. 在 `acceptance.yaml` 顶层加入 `superseded_by: <new-path>`
4. 更新 `tree_index.yaml` 中节点 `status: deprecated`

---

### 步骤 5（delete 模式）：删除节点目录（危险操作）

执行前二次确认：

```
危险操作确认：
将永久删除目录：specs/feature-tree/<node-path>/
包含文件数：N 个
确认删除？[yes/NO]
```

确认后：删除目录 + 从 tree_index.yaml 移除该节点所有条目。

---

## 过期检测快捷触发

在 `/verify`、`/dev` 自动归档完成后，自动触发轻量过期扫描：
- 只检测 1E（归档未回写）— BLOCKING
- 只检测 1B（僵尸引用）— BLOCKING
- 其他 WARNING 项仅在 `/prune scan` 时全量扫描

---

## 与其他命令的关系

| 命令 | 触发时机 |
|------|---------|
| `/prd update` | 更新节点时若父节点已 cancelled/deprecated，警告用户 |
| `/archive` | 补归档后触发轻量过期扫描（1B + 1E） |
| `/verify` | 漂移报告后触发轻量过期扫描（1B + 1E） |
| `/prune scan` | 手动触发全量过期扫描 |
| `make gate` / `make gate-full` | 自动检测 BLOCKING 项（孤儿目录、僵尸引用） |
