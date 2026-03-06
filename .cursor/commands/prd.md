---
name: /prd
id: prd
category: Workflow
description: 需求规格基线（SDD 第一阶段：探索后 → 冻结 spec + 验收标准草稿）
---

> SDD 主流程：explore → **prd** → design → dev → archive → commit → deploy

## 阶段准入自检（PRD Gate）

进入本阶段前，AI Agent **必须自检**以下问题。任何未澄清项 → 输出 `GATE_BLOCK`，暂停执行，建议先执行 `/explore` 补充信息。

| # | 自检问题 | 通过条件 |
|---|---------|---------|
| P1 | 能否用一句话描述"这个特性为谁解决什么问题"？ | 可明确表达目标用户 + 核心问题 |
| P2 | 特性树节点路径是否已确定？ | 可写出 L1/L2/L3/L4 路径（查 `specs/feature-tree/tree_index.yaml`） |
| P3 | 涉及的业务对象是否已识别？ | 能列出实体/聚合/服务，并判断「已存在」或「需新建」 |
| P4 | 是否能列出至少 3 条可量化的验收标准？ | 有具体可测的成功判定条件 |
| P5 | 需求边界是否明确（包括不做什么）？ | 有 out-of-scope 描述，防止范围蔓延 |

**任一未通过 → 输出 GATE_BLOCK，停止执行，列出需澄清项：**

```
GATE_BLOCK（PRD 准入未满足）：
□ P2: 特性树路径不明确 → 先执行 /explore 确认 L4 归属
□ P4: 验收标准不足 → 至少需要 3 条可测量条件
（列出所有未通过项）
```

---

## 两种执行模式

| 模式 | 触发条件 | 行为 |
|------|----------|------|
| **create**（默认）| 目标节点路径不存在 | 创建节点目录 + spec.md + acceptance.yaml 草稿 |
| **update** | 目标节点路径已存在 | diff 现有 spec，追加新内容/变更点（不覆盖已有内容） |

---

## 执行步骤

### 步骤 1：特性树节点定位或创建

1. 查 `specs/feature-tree/tree_index.yaml`，确认目标 L4 节点路径
2. 若节点不存在，创建目录：
   ```bash
   bash scripts/new_feature_fullstack.sh "<slug>"
   ```
3. 更新 `specs/feature-tree/tree_index.yaml`，添加节点条目（status: `specified`）

**节点层级规范**：L4 默认叶子，L5 仅当 L4 需 subtask 分解时使用；不得为每个 L4 机械建 L5（见 `specs/feature-tree/01_FEATURE_TREE_LEVEL_DEFINITIONS.md`）。

---

### 步骤 2：撰写 spec.md

内容结构（严格遵守，禁止在节点下生成 analysis-*.md、README、独立规划书等；详见 `specs/feature-tree/00_FEATURE_TREE_STANDARD.md`）：

```markdown
# <特性标题>

## 背景与动机
<为什么需要这个特性，解决什么问题>

## 目标用户
<谁会使用这个特性>

## 功能范围
<做什么，逐条列出>

## 不做什么（Out of Scope）
<明确排除项，防止范围蔓延>

## 约束
<技术约束、业务约束、时间约束>

## 验收重点
<与 acceptance.yaml 对应的关键验收维度（非详细标准，详见 acceptance.yaml）>
```

---

### 步骤 3：撰写 acceptance.yaml 草稿

```yaml
feature: <feature-slug>
level: L4_object_task  # 按 01_FEATURE_TREE_LEVEL_DEFINITIONS.md 取值
archived: false
level_acceptance:
  - id: A1
    description: "<可量化的验收标准，如：用户可在 3 秒内看到结果>"
    status: pending
    tests: []
  - id: A2
    description: "..."
    status: pending
    tests: []
  # ... A3~An
```

**此阶段 acceptance.yaml 要求**：
- status 可为 `pending`（/design → /dev 阶段完善）
- 至少 3 条 An，每条须满足 SMART 原则（可测量、有明确判定方式）
- 禁止模糊描述（如"用户体验好"、"响应快"）

---

### 步骤 4：输出 PRD 完成摘要

```
PRD 完成：<feature-path>

特性节点：<L1/L2/L3/L4>

spec.md：
  目标用户：<>
  功能范围：<N 条>
  Out of scope：<N 条>

acceptance.yaml：
  A1~AN：<N 条，status=pending>

下一步：/design <feature-path>（方案设计 + 元数据基线）
```

---

## 与其他命令的关系

| 命令 | 职责 | 时机 |
|------|------|------|
| `/explore` | 探索思考，不写任何文件 | PRD 前 |
| `/prd` | **需求规格基线**：spec + acceptance 草稿 | 探索完成后 |
| `/design` | 设计方案 + metadata + codegen | PRD 完成后 |
| `/dev` | 逐 task 实施 | design 完成后 |
| `/try` | 跳过特性树，快速原型验证 | 需求尚不明确时 |
