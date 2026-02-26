---
name: /opsx-ff
id: opsx-ff
category: Workflow
description: 特性基线化（Plan → 文档 + 元数据 + 代码 一次完成，自动 G0/G1）
---

> 主线：`specs/00_MASTER_DEVELOPMENT_FLOW.md` — 阶段 1+2
>
> **设计原则**：Plan 结束后的下一步是**基线化**（Baseline）——特性文档、元数据 YAML、
> 生成代码三者在同一次执行中产生并对齐。不再需要先 `/opsx-ff` 写文档、再手动 `/qwq-extend` 写 YAML。
> `/qwq-extend` 仅用于实施阶段的**增量扩展**（见 qwq-extend.md）。

---

## 两种执行模式

| 模式 | 触发条件 | 行为 |
|------|----------|------|
| **create**（默认）| 目标节点路径不存在 | 创建四类文档 + 元数据 + 代码基线 |
| **update** | 目标节点路径已存在 | diff 现有文档 + 合并新内容 + 补充元数据变更 + 重新运行 codegen |

`update` 模式下**不覆盖**已有内容：spec/design 追加新决策，tasks 追加新任务（不改已完成标记），acceptance 追加新验收项（不改已有 A 编号）。

---

## 前置条件检查（执行前必须满足）

| # | 检查项 | 判定方式 |
|---|--------|----------|
| 1 | 需求已映射到特性树节点 | 可明确写出目标路径：L1/L2/L3/L4 |
| 2 | 涉及的业务对象已识别 | 能列出实体/聚合/服务，并判断「已存在」或「需新建」 |
| 3 | 元数据意图已明确 | 已判断需要哪些元数据操作（见下方「元数据意图表」） |
| 4 | 特性树分解符合规范 | L4 默认叶子，L5 仅当 L4 需 subtask 分解时建 |

**若不满足**：输出补全列表，不执行。

```
前置条件不满足，请先完成以下项：

□ [ ] 需求澄清：用 ask 或 /opsx-explore 明确需求范围
□ [ ] 特性树归属：L1/L2/L3/L4 路径（查 specs/feature-tree/tree_index.yaml）
□ [ ] 业务对象：实体/聚合/服务已识别，标记「已存在」或「需新建」
□ [ ] 元数据意图：确认需要哪类元数据操作（新建聚合/新增字段/新增端点/横切层...）
□ [ ] 分解合规：符合 L4 默认叶子规范（见 01_FEATURE_TREE_LEVEL_DEFINITIONS.md）
```

---

## 执行步骤

### 步骤 1：G0 — Plan 约束检查

```
✓ 需求已映射到特性树节点
✓ 业务对象已在 contracts/metadata/ 中确认（存在或标记需新建）
✓ 任务拆解顺序已确定（metadata → codegen → 业务逻辑 → 测试）
✓ 特性树分解符合层级规范
```

---

### 步骤 2：特性文档（四类制品）

**特性树文档标准**：仅使用四类文档（`spec.md`、`design.md`、`tasks.md`、`acceptance.yaml`）；
禁止在节点下生成 analysis-*.md、README 等独立文档；详见 `specs/feature-tree/00_FEATURE_TREE_STANDARD.md`。

1. 在特性树中定位或新增节点（查 `specs/feature-tree/tree_index.yaml`）
2. 创建特性实例目录（如需要）：
   ```bash
   bash scripts/new_feature_fullstack.sh "<slug>"
   ```
3. 补齐/更新四类制品：
   - `spec.md` — 功能说明、范围、约束、验收重点
   - `design.md` — 设计动因、多方案对比、选型决策、演进路径；**须遵循设计原则**（见标准 2.2）
   - `tasks.md` — 任务拆解，顺序：**metadata → codegen → 业务逻辑 → 测试**；可含「规划任务」小节
   - `acceptance.yaml` — A1~An 验收标准、focus_groups、execution

---

### 步骤 3：元数据基线执行

**这是合并的核心步骤**。根据步骤 1 识别的元数据意图，直接执行对应操作——不再要求用户另行运行 `/qwq-extend`。

#### 元数据意图表

| 意图 | 对应操作 | 产出 |
|------|----------|------|
| 新建聚合根 | 创建 `contracts/metadata/{domain}/{agg}/` + 5 个 YAML 骨架 | aggregate/fields/storage/events/service |
| 新建独立实体 | 创建 `contracts/metadata/{domain}/{entity}/` + 5 个 YAML 骨架 | entity/fields/storage/events/service |
| 新建微服务 | 创建 `contracts/metadata/{domain}/` + `services/{name}-service/` 目录结构 | 完整服务骨架 |
| 新增 API 端点 | 更新 `service.yaml` api_routes | 新路由声明 |
| 新增字段 | 更新 `fields.yaml` | 字段定义 |
| 新增领域事件 | 更新 `events.yaml` | 事件声明 |
| 新增 ReadModel 投影 | 创建 `{entity}/projections/{name}.yaml` | 投影声明 |
| 新增错误码层 | 创建 `{entity}/errors.yaml` | 结构化错误码声明 |
| 新增行为采集层 | 创建 `{entity}/behaviors.yaml` | 行为事件 + 推荐特征 + 训练样本 |
| 新增隐私策略层 | 创建 `{entity}/privacy.yaml` | PII 日志策略 + 数据生命周期 |
| 新增端侧配置层 | 创建 `{entity}/ui_config.yaml` | tab/布局/feature flags/空状态 |
| 新增三层测试契约 | 创建 `{entity}/tests/mock.yaml` + `contract.yaml` + `e2e.yaml` | 测试场景声明 |
| 新增向量能力 | 更新 `aggregate.yaml` + 创建 `_vectors/{name}.yaml` | 向量索引声明 |
| 新增缓存层 | 更新 `aggregate.yaml` + `storage.yaml` | Redis 缓存配置 |
| 无元数据变更 | 跳过本步骤 | — |

**多意图组合**：一个特性可以包含多个意图，按上表顺序逐一执行，每项完成后继续下一项（不单独运行 verify，统一在步骤 4 一次性验证）。

**骨架内容标准**：新建 YAML 时，从同类已有 YAML 中继承结构，预填已知字段，留 TODO 标记待补充项。禁止空文件。

---

### 步骤 4：G1 — Verify + Codegen（自动执行，一次性）

步骤 2+3 全部完成后，AI Agent **必须立即自动执行**：

```bash
make verify-metadata           # metadata 内部一致性（含新增 YAML 格式校验）
make codegen                   # 云侧代码生成（Go struct/repo/routes/errors/behaviors）
make codegen-app               # 端侧代码生成（Dart DTO/错误码/行为tracker/ui配置）
# 若涉及 rec-model-service：
# make codegen-rec-model-python  # Python 特征 schema 生成
```

**任一失败 → 停止 + 输出错误 + 修复建议 → 修复后重跑步骤 4。**

---

### 步骤 5：基线产出摘要

```
基线化完成：<feature-path>

特性文档：
  ✓ spec.md     — <范围摘要>
  ✓ design.md   — <关键设计决策>
  ✓ tasks.md    — <N 个任务>
  ✓ acceptance  — A1~An

元数据变更：
  ✓ <变更1>（如：新建 contracts/metadata/content/post/errors.yaml）
  ✓ <变更2>（如：更新 contracts/metadata/content/post/service.yaml +2 路由）
  ...

代码基线：
  ✓ make verify-metadata PASS
  ✓ make codegen PASS  →  <生成文件列表>
  ✓ make codegen-app PASS  →  <生成文件列表>

下一步：/opsx-deliver <feature-path>（验收驱动交付）
      或 /opsx-apply <feature-path>（逐 task 实施）
```

---

## 与其他命令的关系

| 命令 | 职责 | 使用时机 |
|------|------|----------|
| `/opsx-explore` | 探索思考，不写任何文件 | Plan 阶段（/opsx-ff 前） |
| `/opsx-ff` | **基线化**：文档 + 元数据 + 代码，一次完成 | Plan 结束后，产生可执行基线 |
| `/qwq-extend` | 实施阶段**增量扩展**（新增字段/事件/端点等） | 实施中发现需要扩展业务对象时 |
| `/opsx-apply` | 逐 task 实施（消费基线产出的 tasks.md） | 基线化完成后 |
| `/opsx-deliver` | 验收驱动的完整交付 | 基线化完成后（推荐） |

> **关键区别**：`/opsx-ff` 创建基线；`/qwq-extend` 在基线上做增量。
> 不再需要在 `/opsx-ff` 完成后手动调用 `/qwq-extend` 来完成"本应在基线时就做好"的元数据。
