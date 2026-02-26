# 特性树 L1-L5 层级定义与分解规范（唯一约定）

> **权威**：本文档是特性树 L1-L5 层级划分与分解的**唯一权威定义**。开发全流程（Plan → Create → Implement → Verify → Submit）中，特性树分解与各卡点须遵从本规范；流程规格与命令已同步引用，见**八、特性树分解与开发卡点落实**及 `specs/00_MASTER_DEVELOPMENT_FLOW.md`、`.cursor/commands/`。

---

## 一、定义与分解原则（开宗明义）

### 1.1 层级定义概要

| 层级 | 语义 | 目录深度 | level 取值 | 分解要点 |
|------|------|----------|------------|----------|
| **L1** | 能力域 | 1 | L1 | 固定 9 个，不新增 |
| **L2** | 特性 | 2 | L2_feature | 具备独立交付价值 |
| **L3** | 子特性/组件 | 3 | L3_subfeature | 有独立契约或模块边界 |
| **L4** | 契约/任务 | 4 | L4_object_task | **默认叶子层**，可落地、可验收 |
| **L5** | 子任务（可选） | 5 | L5 / L5_subtask | **仅当 L4 任务过大需拆成多个子任务时**使用 |

### 1.2 分解过程（必须遵从）

1. **归属 L1**：需求先归属既有 L1，不新增 L1。
2. **L2**：可独立交付、可单独规划迭代 → 建 L2。
3. **L3**：有独立契约或模块边界 → 建 L3。
4. **L4**：可对应具体契约/策略/实现任务 → 建 L4；**L4 即默认叶子**，大多数特性止于 L4。
5. **L5**：仅当该 L4 任务足够大、需拆成 **≥2 个独立可验收子任务** 时才建 L5；否则不建 L5。

### 1.3 避免（负面示例）

- **禁止**多套 level 命名混用（如 L5_leaf / L5_cross_cutting 与 L5_subtask 混用；统一用 L5 或 L5_subtask）。
- **禁止**为每个 L4 机械地建一个 L5（如「契约 + guard」拆成两个节点）；guard 等应合并进 L4 的 spec/tasks。
- **禁止**无独立契约或模块边界就拆 L3，或无具体可验收任务就拆 L4。

---

## 二、统一层级定义（详细）

**原则**：层级由**目录深度**唯一确定。L4 为默认叶子层；L5 仅当 L4 任务需 subtask 分解时使用。

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

### 2.4 L4：契约/任务（Contract / Object-task）——**默认叶子层**

| 属性 | 定义 |
|------|------|
| **语义** | L3 下的**具体契约、策略或实现任务**，是可直接映射到 metadata/codegen/手写逻辑的粒度。**L4 为默认叶子层**，大多数特性树止于 L4。 |
| **目录** | `specs/feature-tree/<L1>/<L2>/<L3>/<l4-name>/` |
| **父子** | 父节点必为 L3（或特殊情况下 L2，见下）。 |
| **level 取值** | `L4` 或 `L4_object_task`（门禁）/ `L4_detail`（tree_index）。**统一为 `L4_object_task`**，表示「可落地的对象级任务」。 |

**分解规则**：

- L4 应对应**可执行、可验收**的交付单元。
- 典型形态：**契约**（如 feed-dto-cursor-contract）、**策略**（如 timeout-circuit-degrade-policy）、**实现任务**（如 mongo-pg-vector-cache-adapters）。
- 若 L3 足够简单，可不拆 L4，L3 即叶子。
- **L4 即叶子**：不强制拆 L5；原先常见的「契约 + guard」「策略 + observability」等应合并进 L4 的 spec/tasks，而非单独建 L5。

**判断标准**：

- 能对应到具体的 API 契约、存储 schema、或 codegen 产物 → L4。
- 有明确的「完成条件」和验收项 → L4。

**示例**：

- `unified-items-cursor` → `feed-dto-cursor-contract`（含游标兼容性保障，无需单独 L5）
- `repository-interface-layering` → `mongo-pg-vector-cache-adapters`

---

### 2.5 L5：子任务（Subtask）——**仅当 L4 任务过大需细分时**

| 属性 | 定义 |
|------|------|
| **语义** | L4 下的**子任务**。**仅当某个 L4 任务足够大、需拆成多个可独立验收的子任务时**才使用 L5。 |
| **目录** | `specs/feature-tree/<L1>/<L2>/<L3>/<L4>/<l5-name>/` |
| **父子** | 父节点必为 L4。 |
| **level 取值** | `L5` 或 `L5_subtask`。 |

**分解规则**：

- **默认不用 L5**：大多数 L4 任务可直接在 tasks.md 中拆解为任务项，无需建 L5 节点。
- **L5 的触发条件**：某个 L4 任务包含**多个独立可验收的子任务**（通常 ≥2 个），且各自有独立 spec/design/acceptance 价值。
- 若 L4 下仅有一个「后续步骤」（如 guard、observability），应将其作为 L4 的一部分写入 spec/tasks，**不要单独建 L5**。

**判断标准**：

- L4 任务可拆成 ≥2 个独立可验收子任务 → 可建 L5。
- L4 任务仅需在 tasks.md 中列若干任务项即可 → 不建 L5。

**示例（需 L5）**：

- L4 `release-rollback-procedure` 拆成：`rollback-trigger-criteria`、`rollback-execution-steps`、`rollback-audit-trace` 三个独立可验收子任务 → 可建 L5。

**示例（不需 L5）**：

- `feed-dto-cursor-contract` + `cursor-compatibility-guard`：guard 作为 cursor 契约的一部分 → 合并进 L4，不建 L5。

---

## 三、统一 level 取值约定

为避免多套命名继续并存，**统一约定**：

| 层级 | 推荐取值 | 说明 |
|------|----------|------|
| L1 | `L1` | 能力域，tree_index 可保留 L1_domain 作为兼容 |
| L2 | `L2_feature` | 特性，与 feature_tree / 门禁一致 |
| L3 | `L3_subfeature` | 子特性/组件，与门禁一致 |
| L4 | `L4_object_task` | 契约/任务，**默认叶子层** |
| L5 | `L5` 或 `L5_subtask` | 仅当 L4 任务需拆成多个子任务时使用 |

**acceptance.yaml** 中 `level` 必须使用上表取值之一。门禁若仍期望 `L5_cross_cutting` 等历史取值，可做兼容映射。

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
是否可对应具体契约/策略/实现任务？
    ├─ 是 → L4（契约/任务）
    └─ 否 → 归入既有 L4
        │
        ▼
该 L4 任务是否足够大、需拆成多个独立可验收子任务？
    ├─ 是（≥2 个子任务）→ L5（子任务）
    └─ 否 → L4 即叶子，不建 L5
```

**原则**：**默认止于 L4**，能合并则合并；仅当 L4 任务过大需 subtask 分解时才建 L5。

---

## 五、与现有体系的映射

### 5.1 tree_index.yaml

- 当前使用：L1_domain, L2_feature, L3_component, L4_detail, L5_leaf
- **建议**：L3 统一为 `L3_subfeature`，L4 统一为 `L4_object_task`；L5 统一为 `L5` 或 `L5_subtask`（仅当 L4 需 subtask 分解时）
- 存量树若已有 L5 节点，可保留；新特性**默认止于 L4**，不轻易建 L5

### 5.2 acceptance.yaml

- 功能域：当前部分使用 L2/L3/L4/L5 无后缀
- **建议**：统一为 L2_feature、L3_subfeature、L4_object_task；L5 用 `L5` 或 `L5_subtask`
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
- [ ] L4 可对应具体契约/策略/实现任务
- [ ] **默认止于 L4**；L5 仅当 L4 任务需拆成 ≥2 个独立可验收子任务时添加
- [ ] acceptance.yaml 的 level 使用统一取值（L2_feature / L3_subfeature / L4_object_task / L5 或 L5_subtask）
- [ ] tree.yaml 与 tree_index.yaml 同步更新

---

## 七、总结

| 层级 | 语义 | 目录深度 | 统一 level | 分解要点 |
|------|------|----------|------------|----------|
| **L1** | 能力域 | 1 | L1 | 固定 9 个，不新增 |
| **L2** | 特性 | 2 | L2_feature | 独立交付价值 |
| **L3** | 子特性/组件 | 3 | L3_subfeature | 独立契约/模块 |
| **L4** | 契约/任务 | 4 | L4_object_task | **默认叶子**，可落地、可验收 |
| **L5** | 子任务（可选） | 5 | L5 / L5_subtask | 仅当 L4 任务过大需拆成多个子任务 |

遵循以上定义，可确保特性树分解**无歧义、概念一致**，所有扩展特性都能正确分解到对应层级。

---

## 八、特性树分解与开发卡点落实

特性树分解须贯穿开发流水线各阶段，在各卡点中被正确落实。详见 `specs/00_MASTER_DEVELOPMENT_FLOW.md`。

### 8.1 G0（Plan）——需求映射与分解合规

| 卡点 | 特性树落实 |
|------|------------|
| 需求已映射到特性树节点 | 明确目标节点：L1 / L2 / L3 / L4（及 L5，若适用）路径 |
| 任务拆解遵循 metadata-first | 任务顺序：metadata → codegen → 业务逻辑 → 测试 |
| 分解合规 | 新建节点须遵循本规范：L4 默认叶子，L5 仅当 L4 需 subtask 分解时 |

**AI Agent 行为**：Plan 时先确认需求归属的 L1/L2/L3/L4，再按层级定义判断是否需要新建节点或建 L5；任务拆解写入目标节点的 tasks.md。

---

### 8.2 G1（Create）——特性创建与四类文档

| 卡点 | 特性树落实 |
|------|------------|
| 创建/更新特性目录 | 路径符合 `specs/feature-tree/<L1>/<L2>/.../<L4|L5>/` |
| 四类文档齐全 | 每个节点：spec.md、design.md、tasks.md、acceptance.yaml |
| tree.yaml 一致 | 新建节点须同步更新对应 L1 的 tree.yaml |
| tree_index 一致 | 若使用 tree_index.yaml，须同步更新 |
| make verify 通过 | metadata 内部一致性 |

**AI Agent 行为**：`/opsx-ff` 或 `/qwq-extend` 创建节点时，按 tree.yaml 结构创建目录、补齐四类文档；acceptance.yaml 中 level 使用统一取值。

---

### 8.3 G2（Implement）——按 tasks 逐项实施

| 卡点 | 特性树落实 |
|------|------------|
| 按 tasks.md 逐项实施 | 每个 task 对应一个可交付单元；L4 节点下 task 直接对应 L4 范围 |
| 每完成一个 task 执行 G2 | make build + make test-contract |
| 实现符合 spec/design | 业务逻辑、契约、字段策略与 spec/design 一致 |

**AI Agent 行为**：`/opsx-apply` 按 tasks.md 顺序执行；若某 L4 有 L5 子节点，L5 对应的子任务可在 tasks.md 中分组或引用，或由 L5 节点独立 tasks 承载。

---

### 8.4 G3（Verify）——tree 与 acceptance 完整性

| 卡点 | 特性树落实 |
|------|------------|
| verify_feature_tree | tree.yaml ↔ 目录 ↔ 四类文档存在性；L1 含 spec.md + tree.yaml |
| tasks.md 完成度 | 当前交付任务已勾选完成 |
| acceptance.yaml A1~A8 | 与 spec/design 对齐，全部满足 |
| make gate-full | 含 verify_feature_tree、verify_metadata、verify_arch_constraints 等 |

**AI Agent 行为**：`/opsx-verify`、`/opsx-archive` 时检查目标节点及子节点的 tasks 完成度、acceptance 满足情况。

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
| Plan | /opsx-explore | L1~L4（+L5 若适用） | 映射到正确节点，分解合规 |
| Create | /opsx-ff, /qwq-extend | 新建 L2/L3/L4/L5 | 四类文档、tree.yaml、acceptance level |
| Implement | /opsx-apply | L4（+L5 子任务） | tasks.md 逐项执行 |
| Verify | /opsx-verify, /opsx-archive | 目标节点及子节点 | tree 一致性、tasks 完成度、acceptance |
| Submit | /submit-with-gate | 变更范围 | specs 变更时 gate-full 含特性树检查 |

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
| `specs/00_MASTER_DEVELOPMENT_FLOW.md` | 各阶段（Plan/Create/Implement/Verify/Submit）中明确特性树层级与分解遵从要求，并引用本文档 |
| `.cursor/commands/opsx-explore.md` | G0：需求映射到节点时须符合层级定义，L4 默认叶子、L5 仅 subtask 分解 |
| `.cursor/commands/opsx-ff.md` | G0/G1：新建节点须符合层级定义；acceptance.yaml level 统一取值 |
| `.cursor/commands/opsx-apply.md` | 实施范围对应 L4（及 L5 子任务）；tasks 与节点层级一致 |
| `.cursor/commands/opsx-verify.md` | G3：特性树一致性含 tree.yaml、acceptance level 与本文档规范 |
| `.cursor/commands/submit-with-gate.md` | G4：specs 变更时 gate-full 含特性树检查 |
