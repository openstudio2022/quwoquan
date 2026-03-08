# 特性树层级定义与分解规范（唯一约定）

> **权威**：本文档是特性树层级划分与分解的**唯一权威定义**。开发全流程（Plan → Create → Implement → Verify → Submit）中，特性树分解与各卡点须遵从本规范；流程规格与命令已同步引用，见**八、特性树分解与开发卡点落实**及 `specs/00_MASTER_DEVELOPMENT_FLOW.md`、`.cursor/commands/`。

---

## 一、定义与分解原则（开宗明义）

### 1.1 层级定义概要（治理视图）

| 层级 | 语义 | 目录深度 | 推荐 level 取值 | 分解要点 |
|------|------|----------|------------------|----------|
| **L1** | 关键能力 | 1 | L1 | 固定顶级能力域，不新增 |
| **L2** | 功能特性 | 2 | L2_feature | 具备独立交付价值 |
| **L3** | 子功能或组件 | 3 | L3_subfeature | 有独立契约或模块边界 |
| **L4** | Story / 最小交付单元 | 4 | L4_story | 默认叶子层，可开发、可验收 |

**兼容说明**：
- 历史节点中仍可能存在 `L1_domain / L3_component / L4_detail / L5_leaf / L5_cross_cutting`。
- 这些命名在迁移完成前继续兼容读取，但**新特性一律按 L1~L4 治理视图建模**。
- 历史 `L5` 视为“兼容层/遗留子任务表达”，不再作为新增特性的默认建模层。

### 1.2 分解过程（必须遵从）

1. **归属 L1**：需求先归属既有 L1，不新增 L1。
2. **L2**：可独立交付、可单独规划迭代 → 建 L2。
3. **L3**：有独立契约或模块边界 → 建 L3。
4. **L4**：可对应一个可独立交付、可独立验收、可绑定测试证据的 **Story** → 建 L4；**L4 即默认叶子**。
5. **历史 L5**：仅用于兼容旧树结构；新特性优先把工程子步骤写入 `tasks.md`，而不是继续扩一层目录。

### 1.3 避免（负面示例）

- **禁止**多套 level 命名继续扩散；新特性不得再新增 `L4_detail`、`L5_leaf`、`L5_cross_cutting`。
- **禁止**把工程实现步骤直接建成树节点；工程步骤应写入 `tasks.md`，交付单元写入 L4 Story。
- **禁止**无独立契约或模块边界就拆 L3，或无明确用户/平台价值与完成定义就拆 L4。

---

## 二、统一层级定义（详细）

**原则**：治理视图以 **L1~L4** 为主。L4 为默认叶子层，代表最小可交付 Story；历史 L5 仅作兼容读取。

### 2.1 L1：能力域（Domain / Capability）

| 属性 | 定义 |
|------|------|
| **语义** | 端云一体化的**顶级能力域**，对应业务或平台的一类完整价值。 |
| **目录** | `specs/feature-tree/<l1-name>/` |
| **父子** | 无父节点；是整棵树的根。 |
| **数量** | 固定 9 个（5 功能 + 4 非功能）。 |
| **level 取值** | `L1` 或 `L1_domain`（tree_index）/ `L1_capability`（feature_tree 历史，可统一为 L1）。 |

**分解规则**：

- L1 不通过任务创建，由 `l1_index.yaml` 与 `tree_index.yaml` 固定。
- 新业务能力必须先归属既有 L1，不得新增 L1（除非平台级架构变更）。

**示例**：`discovery-content`、`circle-community`、`runtime`、`gateway-orchestrator-foundation`。

---

### 2.2 L2：特性（Feature）

| 属性 | 定义 |
|------|------|
| **语义** | L1 下的**主要特性/特性域**，具备独立交付价值，可单独规划迭代。 |
| **目录** | `specs/feature-tree/<L1>/<l2-name>/` |
| **父子** | 父节点必为 L1。 |
| **level 取值** | `L2` 或 `L2_feature`（统一使用 `L2_feature` 与门禁一致）。 |

**分解规则**：

- 一个 L2 对应一个**端到端用户可感知能力**或**平台级可独立交付模块**。
- L2 不宜过多：每个 L1 下建议 2~5 个 L2。
- 若某能力无法归入任一 L2，应优先扩展既有 L2 的 scope，而非轻易新增 L2。

**判断标准**：

- 能独立写成「用户故事」或「平台能力说明」的一整块能力 → L2。
- 需要多个服务/端侧模块协作完成 → L2。

**示例**：

- `discovery-content` → `feed-orchestration-recommendation`、`publish-comment-reaction`、`media-processing-helper-read`
- `runtime` → `runtime-config`、`runtime-errors`、`runtime-repository`

---

### 2.3 L3：子特性/组件（Sub-feature / Component）

| 属性 | 定义 |
|------|------|
| **语义** | L2 下的**子能力或组件**，是 L2 的能力组成单元，通常对应一个服务内模块或跨服务子链路。 |
| **目录** | `specs/feature-tree/<L1>/<L2>/<l3-name>/` |
| **父子** | 父节点必为 L2。 |
| **level 取值** | `L3` 或 `L3_subfeature`（门禁）/ `L3_component`（tree_index）。**统一为 `L3_subfeature`**，与门禁和 feature_tree 一致。 |

**分解规则**：

- 一个 L3 对应 L2 内的一类**可独立设计、可单独测试**的子能力。
- L3 通常有明确的**契约边界**（API、事件、存储模型之一）。
- 若某逻辑仅为 L2 的实现细节且无独立契约，不必单独拆 L3。

**判断标准**：

- 有独立的 spec/design，且可被其他 L3 或上层复用 → L3。
- 对应独立接口、独立存储模型、独立事件流 → L3。

**示例**：

- `feed-orchestration-recommendation` → `unified-items-cursor`、`personalized-ranking`、`feed-fallback-degrade`
- `runtime-repository` → `repository-interface-layering`

---

### 2.4 L4：Story / 最小交付单元——**默认叶子层**

| 属性 | 定义 |
|------|------|
| **语义** | L3 下的**最小可交付 Story**，是可直接映射到 spec/design/acceptance/tasks/test evidence 的粒度。**L4 为默认叶子层**，大多数新特性树止于 L4。 |
| **目录** | `specs/feature-tree/<L1>/<L2>/<L3>/<l4-name>/` |
| **父子** | 父节点必为 L3（或特殊情况下 L2，见下）。 |
| **level 取值** | 推荐 `L4_story`；迁移期兼容 `L4_object_task` / `L4_detail`。 |

**分解规则**：

- L4 应对应**可执行、可验收、可追溯到测试层**的交付单元。
- 典型形态：一个用户 Story、一个平台 Story、一个契约型 Story、一个跨端云交付 Story。
- 若 L3 足够简单，可不拆 L4，L3 即叶子。
- **L4 即叶子**：工程子步骤进入 `tasks.md`；不要再为“guard/observability/适配器”机械建层级。

**判断标准**：

- 能对应到具体的用户/平台价值、契约变更或交付边界 → L4。
- 有明确的「完成定义」、验收项和测试层映射 → L4。

**示例**：

- `unified-items-cursor` → `feed-dto-cursor-story`
- `repository-interface-layering` → `mongo-pg-vector-cache-story`

---

### 2.5 历史 L5：兼容子任务层（Legacy Compatibility）

| 属性 | 定义 |
|------|------|
| **语义** | 对历史树结构的兼容表达。新模型中，工程子步骤原则上通过 `tasks.md` 表达，而不是继续下钻目录。 |
| **目录** | `specs/feature-tree/<L1>/<L2>/<L3>/<L4>/<legacy-l5-name>/` |
| **父子** | 父节点为历史 L4。 |
| **level 取值** | `L5` / `L5_subtask` / 历史 `L5_leaf` / `L5_cross_cutting`。 |

**分解规则**：

- **新特性默认不用 L5**：大多数 Story 直接在 `tasks.md` 中拆解为任务项。
- **仅兼容旧节点**：已有 L5 可保留，直到对应 L4 Story 完成收敛迁移。
- 若只是一个 Story 的实现步骤、增强项或风险控制项，应写入 L4 的 spec/design/tasks，**不要新建 L5**。

**判断标准**：

- 历史节点已使用 L5，可保留并逐步回收。
- 新增需求若仅需在 `tasks.md` 中列若干任务项即可完成 → 不建 L5。

**示例（需 L5）**：

- L4 `release-rollback-procedure` 拆成：`rollback-trigger-criteria`、`rollback-execution-steps`、`rollback-audit-trace` 三个独立可验收子任务 → 可建 L5。

**示例（不需 L5）**：

- `feed-dto-cursor-contract` + `cursor-compatibility-guard`：guard 作为 cursor 契约的一部分 → 合并进 L4，不建 L5。

---

## 三、统一 level 取值约定

为避免多套命名继续并存，**统一约定**：

| 层级 | 推荐取值 | 说明 |
|------|----------|------|
| L1 | `L1` | 关键能力，tree_index 可保留 L1_domain 作为兼容 |
| L2 | `L2_feature` | 功能特性 |
| L3 | `L3_subfeature` | 子功能或组件 |
| L4 | `L4_story` | Story / 最小交付单元，默认叶子层 |
| Legacy L5 | `L5` / `L5_subtask` | 仅迁移期兼容，不作为新增默认取值 |

**acceptance.yaml** 中 `level` 必须优先使用上表取值；历史 `L4_object_task / L4_detail / L5_*` 可做兼容映射。

---

## 四、分解决策树

```
需求/能力
    │
    ▼
是否属于既有 L1？
    ├─ 否 → 归属既有 L1（不新增 L1）
    └─ 是
        │
        ▼
是否可独立交付、独立规划迭代？
    ├─ 是 → L2（特性）
    └─ 否 → 归入既有 L2
        │
        ▼
是否有独立契约/模块边界？
    ├─ 是 → L3（子特性）
    └─ 否 → 归入既有 L3
        │
        ▼
是否可形成独立交付、独立验收、独立测试映射的 Story？
    ├─ 是 → L4（Story）
    └─ 否 → 归入既有 L4
```

**原则**：**默认止于 L4**，L4 代表 Story；工程步骤进入 `tasks.md`，历史 L5 仅作兼容。

---

## 五、与现有体系的映射

### 5.1 tree_index.yaml

- 当前使用：L1_domain, L2_feature, L3_component, L4_detail, L5_leaf
- **目标**：L3 统一为 `L3_subfeature`，L4 统一为 `L4_story`
- 存量树若已有 L5 节点，可保留；新特性**默认止于 L4 Story**

### 5.2 acceptance.yaml

- 功能域：当前部分使用 L2/L3/L4/L5 无后缀
- **目标**：统一为 L2_feature、L3_subfeature、L4_story；Legacy L5 仅兼容读取
- 门禁脚本 `verify_feature_traceability.sh` 若期望 L5_cross_cutting 等，可做兼容映射

### 5.3 changes/feature_tree.yaml

- 已使用 L1_capability, L2_feature, L3_subfeature, L4_object_task, L5_cross_cutting
- **建议**：L5 统一为 `L5` 或 `L5_subtask`；新特性默认止于 L4

---

## 六、扩展特性分解检查清单

新增或扩展特性时，按以下清单自检：

- [ ] 已归属正确 L1
- [ ] L2 具备独立交付价值，非 L1 的简单子集
- [ ] L3 有独立契约或模块边界
- [ ] L4 可对应一个最小可交付 Story
- [ ] **默认止于 L4**；工程子步骤进入 `tasks.md`
- [ ] acceptance.yaml 的 level 优先使用统一取值（L2_feature / L3_subfeature / L4_story）
- [ ] tree.yaml 与 tree_index.yaml 同步更新

---

## 七、总结

| 层级 | 语义 | 目录深度 | 统一 level | 分解要点 |
|------|------|----------|------------|----------|
| **L1** | 关键能力 | 1 | L1 | 固定顶级能力域 |
| **L2** | 功能特性 | 2 | L2_feature | 独立交付价值 |
| **L3** | 子功能或组件 | 3 | L3_subfeature | 独立契约/模块 |
| **L4** | Story / 最小交付单元 | 4 | L4_story | **默认叶子**，可开发、可验收 |
| **Legacy L5** | 历史子任务兼容层 | 5 | L5 / L5_subtask | 仅迁移期兼容 |

遵循以上定义，可确保特性树分解**无歧义、概念一致**，所有扩展特性都能正确分解到对应层级。

---

## 八、特性树分解与开发卡点落实

特性树分解须贯穿开发流水线各阶段，在各卡点中被正确落实。详见 `specs/00_MASTER_DEVELOPMENT_FLOW.md`。

### 8.1 G0（Plan）——需求映射与分解合规

| 卡点 | 特性树落实 |
|------|------------|
| 需求已映射到特性树节点 | 明确目标节点：L1 / L2 / L3 / L4 路径 |
| 任务拆解遵循 metadata-first | 任务顺序：metadata → codegen → 业务逻辑 → 测试 |
| 分解合规 | 新建节点须遵循本规范：L4 默认叶子，L5 仅当 L4 需 subtask 分解时 |

**AI Agent 行为**：Plan 时先确认需求归属的 L1/L2/L3/L4，再按层级定义判断是否需要新建节点；工程任务拆解写入目标节点的 `tasks.md`。

---

### 8.2 G1（Create）——特性创建与四类文档

| 卡点 | 特性树落实 |
|------|------------|
| 创建/更新特性目录 | 路径符合 `specs/feature-tree/<L1>/<L2>/<L3>/<L4>/` |
| 四类文档齐全 | 每个节点：spec.md、design.md、tasks.md、acceptance.yaml |
| tree.yaml 一致 | 新建节点须同步更新对应 L1 的 tree.yaml |
| tree_index 一致 | 若使用 tree_index.yaml，须同步更新 |
| make verify 通过 | metadata 内部一致性 |

**AI Agent 行为**：创建节点时，按四层治理视图创建目录、补齐四类文档；acceptance.yaml 中优先使用 `L4_story` 等统一取值。

---

### 8.3 G2（Implement）——按 tasks 逐项实施

| 卡点 | 特性树落实 |
|------|------------|
| 按 tasks.md 逐项实施 | `tasks.md` 是 Story 的工程执行清单，不是树层级 |
| 每完成一个 task 执行 G2 | make build + make test-contract |
| 实现符合 spec/design | 业务逻辑、契约、字段策略与 spec/design 一致 |

**AI Agent 行为**：按 Story 驱动实施，`tasks.md` 记录 Story 的工程步骤；历史 L5 若存在，仅作为兼容引用。

---

### 8.4 G3（Verify）——tree 与 acceptance 完整性

| 卡点 | 特性树落实 |
|------|------------|
| verify_feature_tree | tree.yaml ↔ 目录 ↔ 四类文档存在性；L1 含 spec.md + tree.yaml |
| tasks.md 完成度 | 当前交付任务已勾选完成 |
| acceptance.yaml A1~A8 | 与 spec/design 对齐，全部满足 |
| make gate-full | 含 verify_feature_tree、verify_metadata、verify_arch_constraints 等 |

**AI Agent 行为**：`/verify` 复核目标节点及子节点的 tasks 完成度、acceptance 满足情况；若自动归档失效，则由 `/archive` 兼容补回写。

---

### 8.5 G4（Submit）——按变更范围审计

| 卡点 | 特性树落实 |
|------|------------|
| specs 变更 | 若变更 specs/feature-tree/，须通过特性树一致性检查（作为 gate-full 一部分） |
| 多范围变更 | 含 specs 时执行 make gate-full |

---

### 8.6 卡点与层级对应关系

| 阶段 | 命令 | 主要涉及的层级 | 特性树相关检查 |
|------|------|----------------|----------------|
| Plan | /explore | L1~L4（+L5 若适用） | 映射到正确节点，分解合规 |
| Create | /prd, /design, /extend | 新建 L2/L3/L4/L5 | 四类文档、tree.yaml、acceptance level |
| Implement | /dev | L4（+L5 子任务） | tasks.md 逐项执行 + 自动归档 |
| Verify | /verify, /archive | 目标节点及子节点 | tree 一致性、tasks 完成度、acceptance |
| Submit | /commit | 变更范围 | specs 变更时 gate-full 含特性树检查 |

---

### 8.7 门禁脚本与特性树

| 脚本/检查 | 特性树相关内容 |
|-----------|----------------|
| `scripts/verify_feature_tree_refactor.sh` | tree_index 存在性、L1 目录与 spec/tree.yaml、runtime L2 四类文档 |
| `make gate-full` | 含 verify_feature_tree |
| `verify_feature_traceability.sh`（若启用） | 期望 level：L1_capability, L2_feature, L3_subfeature, L4_object_task, L5_*；可做兼容映射 |

### 8.8 与流程、命令的同步

本「八、特性树分解与开发卡点落实」已同步到以下位置，确保全流程遵从：

| 文档/命令 | 同步内容 |
|-----------|----------|
| `specs/00_MASTER_DEVELOPMENT_FLOW.md` | 各阶段（Explore/PRD/Design/Dev/Verify/Commit）中明确特性树层级与分解遵从要求，并引用本文档 |
| `.cursor/commands/explore.md` | G0：需求映射到节点时须符合层级定义，L4 默认叶子、L5 仅 subtask 分解 |
| `.cursor/commands/prd.md` / `.cursor/commands/design.md` | G0/G1：新建节点须符合层级定义；acceptance.yaml level 统一取值 |
| `.cursor/commands/dev.md` | 实施范围对应 L4（及 L5 子任务）；tasks 与节点层级一致，并在收口时自动归档 |
| `.cursor/commands/verify.md` | G3：特性树一致性含 tree.yaml、acceptance level 与本文档规范 |
| `.cursor/commands/commit.md` | G4：specs 变更时 gate-full 含特性树检查 |
