---
name: /land
id: land
category: Workflow
description: 原型落地基线化（/try 验证通过后 → 逆向提取规格+设计 → 人工确认 → 归档基线）
---

> 前置：已完成 `/try` 并验证成功。
> 目的：将原型成果"落地"为正式的特性树节点，建立规格、设计和代码基线。

**核心流程**：

```
/try 验证通过 → /land 提取草稿（dry-run 预览）→ 人工确认 → 写入特性树 → /archive 基线归档
```

---

## 执行步骤

### 步骤 1：回顾原型产出

扫描原型实现，收集以下信息：

1. **实际实现了什么**：功能点、数据流、API 接口
2. **关键技术决策**：用了什么方案，为什么选这个方案
3. **元数据变更**：新建/修改了哪些 `contracts/metadata/` YAML
4. **代码变更范围**：`git diff --name-only` 查看变更文件清单
5. **发现的约束和取舍**：什么没做、为什么、将来如何处理
6. **对标输入与验证结论**：原型是否参考了标杆产品、原型、公开代码或公开技术文档；哪些结论应被正式吸收

---

### 步骤 2：提取并撰写四类制品草稿

#### 2a. spec.md 草稿

从原型实现逆向推导需求规格（参照 `/prd` 的内容结构）：
- 背景与动机：从原型验证目标提取
- 功能范围：从实际实现的功能点提取
- 不做什么：从原型中未实现的部分 + 发现的取舍提取
- 约束：从原型中遇到的技术/业务约束提取
- 对标输入与吸收结论：从原型阶段参考样本中提取

#### 2b. design.md 草稿

从原型关键技术决策提取（参照 `/design` 的内容结构）：
- 方案对比：原型选用的方案 vs. 放弃的方案（即使是隐性决策）
- 选型决策：选用原型方案的理由
- 关键设计决策：已定不变的决策
- 未来演进：原型中有意保留的技术债或演进点

#### 2c. tasks.md 草稿

从原型已完成工作整理：
- **当前交付任务**：所有原型中完成的工作，全部标 `[x]`
- **搁置任务**：原型中发现但未做的工作（含明确重启条件）
- **未来演进任务**：与 design.md 未来演进对应

#### 2d. acceptance.yaml 草稿

从原型验证结果生成：
- 原型中**已验证**的能力 → status: `implemented`（须补充 `tests[]` 文件链接）
- 原型中**未测试**的验收项 → status: `deferred`（记入 tasks.md 搁置任务）
- 每条核心验收项补齐 `test_layers`（`T1~T4`）
- 禁止保留 status: `pending`（land 完成时所有项必须为 implemented/waived/deferred）

---

### 步骤 3：Dry-run 预览（等待人工确认）

输出完整预览，**不执行任何写入**，等待用户确认：

```
Land 预览（Dry-run）
═══════════════════════════════════════════════════════════

建议特性树路径：<L1>/<L2>/<L3>/<L4-slug>
（如有疑问，请指定正确路径后重试）

spec.md 草稿：
  目标用户：<>
  功能范围：<N 条>
  Out of scope：<N 条>
  约束：<N 条>

design.md 草稿：
  选定方案：<方案名称>
  关键决策：<N 条>
  未来演进：<N 条>

tasks.md 草稿：
  已完成 [x]：<N 条>
  搁置任务：<N 条>（含重启条件）
  未来演进：<N 条>

acceptance.yaml 草稿：
  implemented：A1~AN（<N 条>，需补 tests[] 链接）
  deferred：<N 条>

元数据变更（原型已做，将正式纳入）：
  <列出已变更的 contracts/metadata/ 文件>

代码变更范围：
  <git diff --name-only 摘要>

═══════════════════════════════════════════════════════════
确认以上内容并写入特性树？[y（确认）/ n（放弃）/ 修改（请说明）]
```

用户选择：
- `y` → 进入步骤 4 正式写入
- `n` → 放弃 land，保留原型代码（用户自行决定后续处理）
- `修改 <内容>` → 更新对应草稿后重新展示预览

---

### 步骤 4：写入特性树（人工确认后）

1. 在 `specs/feature-tree/tree_index.yaml` 注册节点（status: `in_progress`）
2. 创建节点目录（若不存在）：
   ```bash
   bash scripts/new_feature_fullstack.sh "<slug>"
   ```
3. 写入 spec.md、design.md、tasks.md、acceptance.yaml（使用步骤 2 的草稿）
4. 若原型中已产生元数据 YAML，确认其完整性（所有必填字段已填，无 TODO 遗漏关键项）

---

### 步骤 5：元数据验证与代码生成

```bash
make verify-metadata           # 确认原型产生的 metadata 格式正确
make codegen                   # 确保 codegen 产物与 metadata 一致
make codegen-app               # 端侧 codegen 一致性
```

任一失败 → 停止，输出修复建议，修复后重跑。

---

### 步骤 6：代码质量检查（产品化验收）

若原型代码存在以下情况，在 tasks.md 中生成**专项重构任务**，在 /commit 前必须完成：

| 检查项 | 违规示例 | 处理方式 |
|--------|---------|---------|
| DDD 分层违规 | domain 层 import infrastructure | 添加重构任务，land 后立即修复 |
| 硬编码视觉字面量 | `fontSize: 16` | 添加重构任务 |
| 错误码硬编码 | `if err.code == 'NOT_FOUND'` | 添加重构任务 |
| 相对路径 import | `import '../utils/...'` | 添加重构任务 |

如发现严重违规（如绕过 metadata 直接操作数据库），提示用户修复后再 land。

---

### 步骤 7：执行归档（/archive 等价）

所有制品写入并通过 codegen 后：

```bash
make gate-full     # G3 全量门禁
```

通过后回写：

```yaml
# acceptance.yaml
archived: true
archived_at: <ISO8601>
```

```yaml
# tree_index.yaml
status: completed
```

---

### 步骤 8：输出落地摘要

```
落地完成（/land）：<feature-path>

原型 → 正式基线
| 制品           | 状态                           |
|----------------|-------------------------------|
| spec.md        | ✓ 写入                        |
| design.md      | ✓ 写入                        |
| tasks.md       | ✓ <N> 条任务（全部 [x]）       |
| acceptance.yaml | ✓ A1~AN（implemented N，deferred N）|
| tree_index.yaml | ✓ 节点注册，status=completed  |

门禁：make gate-full PASS

重构任务：<N> 条（需在 /commit 前完成）

下一步：
  - 若有重构任务 → 完成后执行 /commit
  - 无重构任务 → 直接执行 /commit 提交代码入库
```

---

## 特殊情况处理

### 原型验证不成功（不需要 /land）

直接记录结论并清理：

```bash
git checkout -- .   # 回滚原型代码（或 git stash）
```

可选择记录实验结论：`docs/experiments/<date>-<topic>.md`。

---

## 与其他命令的关系

| 命令 | 作用 | 与 /land 关系 |
|------|------|--------------|
| `/try` | 快速原型验证 | land 的前置 |
| `/land` | **原型落地基线化** | try 验证成功后的必须步骤 |
| `/prd` + `/design` | 标准正向规格→设计流程 | land 是 prd+design 的逆向提取等价版本 |
| `/archive` | 归档特性 | land 的步骤 7 等价于 archive |
| `/commit` | 提交代码入库 | land 完成后执行 commit |
