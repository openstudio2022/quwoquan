# 特性树文档标准（唯一约定）

> **权威**：特性树下所有节点的需求、设计、任务与验收**仅通过以下四类文档表达**。禁止在节点下生成上述四类以外的独立文档（如 `analysis-*.md`、`README.md`、单独「设计说明」「规划书」等）；所有内容必须汇入 spec / design / tasks / acceptance。

---

## 一、四类文档（强制）

每个特性树节点（L1~L5）必须具备且仅依赖以下四类制品：

| 文档 | 用途 | 必须 |
|------|------|------|
| **spec.md** | 功能说明、范围、约束、验收重点；「做什么」「不做什么」 | 是 |
| **design.md** | 设计决策、架构/拓扑、与上下游契约、迁移或演进说明；「怎么做」「为何这样拆」 | 是 |
| **tasks.md** | 可执行任务列表（含当前交付与可选规划任务）；顺序：metadata → codegen → 业务逻辑 → 测试 | 是 |
| **acceptance.yaml** | A1~A8 验收标准、focus_groups、level_acceptance、execution（gate） | 是 |

- **禁止**：在 `specs/feature-tree/<path>/` 下新增 `analysis-*.md`、`README.md`、`*-规划.md`、`*-设计说明.md` 等独立文件；分析、规划、设计说明一律写入上述 **spec.md / design.md / tasks.md**，必要时在 tasks 中增加「规划任务」小节。
- **追溯**：若项目使用 `traceability.yaml`，可保留；验收以 **acceptance.yaml** 为准。

---

## 二、质量与详细度要求

生成或更新四类文档时，须满足以下要求，以便后续特性树一致性与门禁检查可执行。

### 2.1 spec.md

- **必须包含**：节点层级（L1~L5）、功能定位、职责边界、与父/子节点关系、约束（技术/契约/运维）、验收标准概要。
- **必须包含（标准化章节）**：**「适用范围与约束」**——明确本节点方案的适用场景、前置条件、不适用或超出范围的情形（任何方案均有局限性，须在 spec 中写清「在什么条件下成立」「什么不负责」），便于后续回顾与裁剪。可与「约束」合并为小节，但须显式出现适用/不适用表述。
- **建议**：用表格列出子节点或对外契约；引用 design.md / tasks.md 避免重复。

### 2.2 design.md

- **必须包含**：设计动因（为何这样拆）、关键决策、与现有系统/契约的对应关系；若涉及迁移或演进，写清「当前态 → 目标态」与已完成步骤。
- **必须包含（标准化章节）**：
  - **「适用场景与约束」**：当前选定方案的**适用场景**（在什么业务/规模/技术条件下成立）、**约束与局限性**（不适用情形、前置条件、已知限制）。任何方案都有局限性或适应场景，design 中必须显式写出，便于回顾与决策。
  - **「未来演进」**：演进方向、目标态与当前态的差距、前置条件或触发条件、与 tasks 中「搁置任务」「未来演进任务」的对应关系；若当前即为目标态则简要说明「暂无演进项」。
- **建议**：部署形态、服务清单、接口归属用表格表达；规划类清单放在 tasks.md，design 中保留演进原则与契约兼容说明。
- **涉及 UI 时**：design 可选增加「编码规范与设计 token」小节，列出将用的 AppSpacing/AppTypography/AppColors；禁止硬编码 width/height/leadingSize/fontSize/EdgeInsets。

**设计原则（design 必须遵循）**：

1. **业界对标与多方案对比**：对设计主题做**业界最佳实践与标杆方案**的详细分析与对比（如 TikTok/Facebook 信息流、双塔/深度模型、训练与推理分离等），在 design 中给出**多个备选方案**（至少 2 个），从职责边界、SLA、可演进性、实施成本等维度对比，并说明**为何选择当前方案**。
2. **最优或可演进到最优**：选定方案须是**当前条件下最具竞争力的方案**，或**具备明确演进路径、可演进到业界最优**；若因资源/时间/依赖限制无法一步到位，应采用**轻量化可行方案**，且不得阻塞后续演进。
3. **轻量方案时的演进与规划任务**：当采用轻量方案而非一步到位时，**design.md** 中必须写明「当前方案与目标最优方案的差距」「演进路径与前置条件」；**tasks.md** 中必须增加**「搁置任务（带规划）」与「未来演进任务」**（见 2.3），便于跟踪与回顾审视。

### 2.3 tasks.md

- **必须包含**：
  - **「当前交付任务」**：本阶段可执行、可验收的任务（可勾选列表）；顺序：metadata → codegen → 业务逻辑 → 测试；与 `/opsx-apply` 执行顺序一致。
  - **「搁置任务（带规划）」**：因依赖/资源/优先级等原因暂不实施的任务，须写明**搁置原因、计划何时/在何条件下重启、由谁或何节点承接**，便于回顾审视与后续跟进。
  - **「未来演进任务」**：与 design 中「未来演进」对应的中长期演进项（可勾选、不阻塞当前交付）；新开特性时在对应节点 spec/design/tasks 中细化。若无搁置或演进，可写「无」或「暂无」，但章节标题须保留以便统一回顾。
- 以上三小节为**标准化结构**，便于门禁与复盘时一致检查；design 采用轻量方案时，「未来演进任务」必须非空且与 design 的「未来演进」对应。
- **含 UI 的 task**：实施完成后须执行 `python3 scripts/verify_dart_semantic.py`，无新增硬编码视觉字面量。
- **含错误码的 task**：须创建/更新 `errors.yaml`（含 l10n_key、user_message.zh/en），云侧 Handler 使用 generated.AppErrorFrom*，端侧使用 *ErrorCode.fromCode().toDisplayMessage(l10n)，测试使用枚举 .code；实施后执行 `python3 scripts/verify_error_code_semantic.py`。

### 2.4 acceptance.yaml

- **必须包含**：`feature`、`level`、`template`（如 A1-A8）、`execution.local_gate` / `full_gate`；L4/L5 须含 `level_acceptance` 的 A1~An 验收项。
- **一致性**：与 spec 中的验收重点、design 中的交付边界对齐；门禁脚本可依赖本文件做完整性检查。
- **含错误码时**：须有验收项「错误码由 errors.yaml 驱动，云侧无硬编码 user_message，端侧无硬编码 code 字符串」；tests 可引用 `*_error_code_contract_test` 或 journey 测试。

#### 验收项结构（交付后必须填写 status 与 tests）

每个 A1~An 验收项须使用以下结构，**在实施阶段完成时回填**：

```yaml
level_acceptance:
  A1:
    criteria: "验收标准描述（与 spec 对齐）"
    status: pending        # pending | implemented | waived | deferred
    linked_tasks: [M1, C1] # 对应 tasks.md 中的任务编号
    tests:                 # 实现后回填，机器可验证
      - file: test/cloud/content/feed_item_dto_contract_test.dart
        functions: [generates_from_metadata, has_do_not_edit_header]
  A2:
    criteria: "..."
    status: implemented
    tests:
      - file: test/features/content/typed_dto_contract_test.dart
        functions: [photo_dto_from_map, video_dto_alias_resolution]
```

**status 取值语义**：
- `pending`：尚未实现（基线化时的初始状态）
- `implemented`：已实现并有测试覆盖（tests[] 非空，且文件/函数存在）
- `waived`：验收项豁免（须在 criteria 后写明豁免原因）
- `deferred`：延期（须在 tasks.md 搁置任务中有对应条目）

**归档前门禁要求**：所有 A1~An 的 status 必须为 `implemented` / `waived` / `deferred`，不得有 `pending`。
`implemented` 项的 `tests[]` 不得为空；`gate.sh check-feature-tree-consistency` 会验证 tests[] 中每个 file/function 确实存在。

---

## 三、与命令、规则的衔接

- **/opsx-ff**：创建或更新特性时，必须补齐或更新 **spec.md、design.md、tasks.md、acceptance.yaml**；不得生成四类以外的文档。
- **/opsx-apply**：按 **tasks.md** 逐项执行；实现须符合 **spec.md** 与 **design.md**；自动将节点 status 推进为 `in_progress`。
- **/opsx-deliver**：Apply 条件就绪后，**以 acceptance.yaml A1~A8 验收标准为驱动**，迭代完成开发 → 验证 → 归档 → 提交入库；一气呵成交付到合入。
- **/opsx-verify、/opsx-archive**：校验 **tasks.md** 完成度与 **acceptance.yaml** A1~A8；正确性对照 **spec.md** 与 **design.md**；归档时回写 `status: completed` 和 `archived: true`。
- **/opsx-prune**：检测并清理过期/作废节点；将节点标记为 `cancelled` 或 `deprecated`；更新 tree_index.yaml。
- **/opsx-explore**：探索结论若需落档，应写入目标节点的 **spec/design/tasks**，不单独生成分析文档。

详见 `.cursor/commands/` 下各命令与 `specs/00_MASTER_DEVELOPMENT_FLOW.md`。

---

## 四、节点生命周期（Node Lifecycle）

每个特性树节点在 `tree_index.yaml` 中通过 `status` 字段跟踪生命周期。

### 4.1 合法 status 取值

| status | 语义 | 触发命令 | 可否归档 |
|--------|------|----------|----------|
| `specified` | 已规格化，待实施（默认初始值） | `/opsx-ff` create | 否 |
| `in_progress` | 实施中（tasks.md 出现首个 `[x]`） | `/opsx-apply` 自动推进 | 否 |
| `completed` | 已归档交付 | `/opsx-archive` 自动回写 | 是 |
| `cancelled` | 需求取消，节点作废 | `/opsx-prune cancel` | — |
| `deprecated` | 被其他节点取代，保留历史 | `/opsx-prune deprecate` | — |

**state machine**：
```
specified ──→ in_progress ──→ completed
    │               │
    └──→ cancelled  └──→ cancelled
    └──→ deprecated └──→ deprecated
```

### 4.2 过期节点（Stale/Expired Node）定义

以下情形视为**潜在过期节点**，由 `/opsx-prune` 或 `gate.sh` 检测并报告：

| 判断条件 | 严重度 | 建议处理 |
|----------|--------|----------|
| `status=specified`，tasks.md 全为 `[ ]`，且 **90 天以上无 git 变更** | WARNING | `/opsx-prune cancel` 或重确认优先级 |
| `status=in_progress`，acceptance.yaml 存在 pending 项，且 **60 天无 git 变更** | WARNING | 重启实施或降为 `specified`/`cancelled` |
| `status=completed` 但 acceptance.yaml 无 `archived: true` | BLOCKING | `/opsx-archive` 回写 `archived: true` |
| `status=cancelled/deprecated` 但 tasks.md 仍有 `[ ]` 任务 | BLOCKING | 清理 tasks.md 中残余任务 |
| 节点目录存在但不在 `tree_index.yaml` 中（孤儿目录） | BLOCKING | 补充到 tree_index 或删除 |
| `tree_index.yaml` 中节点路径指向不存在的目录 | BLOCKING | 修复路径或删除索引条目 |

### 4.3 取消与废弃（Cancel vs Deprecate）

- **`cancelled`**：需求被明确放弃，目录保留（历史参考），不再出现在 gate 报告的活跃检查中。
  - 必须在 spec.md 顶部加注 `> **CANCELLED**: <取消日期> — <取消原因>`
  - tasks.md 中 `[ ]` 任务须改为 `~~[ ]~~`（Markdown 删除线）或清空

- **`deprecated`**：需求被更优方案取代，需要在 spec.md 中写明替代节点路径。
  - 必须在 spec.md 顶部加注 `> **DEPRECATED**: 已由 <替代路径> 取代`
  - acceptance.yaml 顶层加入 `superseded_by: <替代节点路径>`

### 4.4 `/opsx-archive` 必须回写 tree_index

归档命令执行成功后，必须更新 `tree_index.yaml`：
```yaml
status: completed   # 从 specified/in_progress 改为 completed
```
以及更新 `acceptance.yaml`：
```yaml
archived: true
archived_at: 2026-03-01T00:00:00Z
```

---

## 五、索引与树结构

- 节点目录与层级以 **tree_index.yaml** 为准；新增节点时同步更新 tree_index。
- 四类文档路径约定：`specs/feature-tree/<L1>/<L2>/.../spec.md`（及同目录下 design.md、tasks.md、acceptance.yaml）。
- 节点 status 生命周期见第四节；gate.sh 的 `check-feature-tree-consistency` 会自动检查 lifecycle 一致性和孤儿目录。

---

## 六、L1-L5 层级定义（引用）

L1~L5 的**唯一权威定义**及**与开发卡点的落实关系**见 `specs/feature-tree/01_FEATURE_TREE_LEVEL_DEFINITIONS.md`。

**简要约定**：

| 层级 | 语义 | 统一 level | 分解要点 |
|------|------|------------|----------|
| L1 | 能力域 | L1 | 固定 9 个，不新增 |
| L2 | 特性 | L2_feature | 具备独立交付价值 |
| L3 | 子特性/组件 | L3_subfeature | 有独立契约或模块边界 |
| L4 | 契约/任务 | L4_object_task | **默认叶子层**，可对应具体契约、策略或实现任务 |
| L5 | 子任务（可选） | L5 / L5_subtask | **仅当 L4 任务过大需拆成多个子任务时**使用 |

**原则**：默认止于 L4；L5 仅当 L4 需 subtask 分解时添加。spec.md 与 acceptance.yaml 中 `level` 取值须与上表一致。
