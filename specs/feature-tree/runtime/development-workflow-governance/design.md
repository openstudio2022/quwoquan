# 设计方案：development-workflow-governance（三层治理重构）

## 设计动因

本特性不是业务功能设计，而是仓库治理系统的结构性重构。上游 `spec.md` 已明确冻结三层目标：

- `L1_capability`
- `L2_feature`
- `L3_story`

并且明确：

- 不再保留 `L4/L5`
- 不再保留记录兼容映射
- 不再让测试层与树层共用 `L*` 语义

因此设计阶段的核心任务，不是继续讨论“四层还是三层”，而是回答：

1. 三层模型如何落到目录、索引、命令、规则、门禁与验收结构上。
2. 如何避免旧脚本、旧树和旧命名继续把仓库拉回四/五层。
3. 如何把一次性迁移风险收敛到可执行的切换窗口和回滚方案内。

## 上游输入评审

### `spec.md` 评审结论

- 目标已经清晰：本次只接受三层治理，不接受兼容方案。
- 交付范围清晰：覆盖特性树、命令、主流程、脚本、索引、门禁与 `acceptance.yaml`。
- Out of scope 清晰：本轮不直接改业务代码，不讨论是否回到微软四层，也不保留双轨并行。
- 风险已识别：最大风险在于旧脚本、旧索引和旧文案同时存在，导致新树回长。

### `acceptance.yaml` 评审结论

- 已有 8 条可测验收项，覆盖三层冻结、命令改写、测试去耦、脚本切换、存量迁移和切换约束。
- 作为设计输入已经足够，不存在阻断设计的缺项。
- 当前最需要补充的是：把这些验收项映射成具体的文档改造、脚本改造和迁移任务序列。

### 阻断项结论

- 无阻断项，可进入设计。

## 对标输入分析

### 对标对象

- Azure DevOps：`Epic -> Feature -> Story -> Task`
- Jira / Atlassian：常见 `Epic/Feature -> Story -> Task`
- Aha!：Theme / Epic / Story / Task

### 借鉴点

- `Story` 必须是最小业务交付与验收单元。
- `Task` 必须服务于 `Story`，而不是继续长成树层级。
- 治理树与测试矩阵应分离，不能用同一套层级名表示两种语义。

### 不借鉴点

- 不采用微软四层，因为当前仓库的核心矛盾是“层级过深、旧新并存、口径漂移”，而不是“缺少中间管理层”。
- 不采用兼容迁移，因为兼容层会使脚手架、门禁和索引长期保留双重逻辑。

### 当前差距

- 目录、索引生成器、脚手架、门禁、命令文案仍然深度绑定旧层级。
- `03-testing.mdc` 已有 `T1~T4` 治理视图，但主流程和 deploy 文案仍混用 `L3/L4` 测试称呼。
- `changes/` 旧脚手架体系与 `specs/feature-tree/` 主树并存，形成第二真相源。

## 方案对比

### 方案 A：文档先收口，脚本后续渐进改造

先改 `spec.md / design.md / tasks.md / acceptance.yaml` 与命令文案，暂不强制脚本零兼容，后续再慢慢迁移生成器和 gate。

**优点**：
- 改动节奏更平滑。
- 文档收口快，设计阻力较低。

**缺点**：
- 旧脚手架和旧索引仍会持续产出旧层级。
- 文档与自动化会长期不一致。
- 用户一旦继续新增节点，旧模型会立刻回流。

**适用条件**：
- 允许长期双轨并存。

### 方案 B：三层文档与自动化分两波切换

第一波统一文档、命令和标准；第二波集中切换脚手架、索引和门禁；中间短暂冻结新特性创建。

**优点**：
- 风险比一次性全改小。
- 比纯文档方案更接近真正切换。

**缺点**：
- 中间冻结期内仍存在旧树残留。
- 两波之间需要维持临时人工纪律。
- 若冻结控制不严，旧节点仍可能混入。

**适用条件**：
- 允许短周期冻结和严格人工管控。

### 方案 C：单窗口一次性切换三层治理（本期选型）

在一个治理分支和切换窗口内，统一完成：

- 三层定义重写
- 命令文案重写
- 主流程重写
- 测试口径去耦
- 脚手架与 tree index 生成器重写
- 门禁脚本改为零兼容
- 存量特性树和 `acceptance.yaml` 全量迁移

**优点**：
- 不会留下长期兼容负担。
- 能保证命令、脚本、树和门禁从切换日开始使用同一套语义。
- 最符合上游规格“不要兼容”的前提。

**缺点**：
- 变更面最大。
- 必须有明确冻结窗口和回滚方案。
- 需要先把设计与任务拆解得足够细，避免执行期混乱。

**适用条件**：
- 已经明确接受一次性治理重构成本，并能在切换窗口内集中推进。

## 选型决策

**选定方案**：方案 C，单窗口一次性切换三层治理。

**理由**：

- 上游规格已经明确排除兼容方案。
- 当前旧树、旧脚本、旧索引、旧命令并存，如果不一次性切换，三层模型会立即被旧工具侵蚀。
- 本次重构目标是“清除记录层级与第二真相源”，不是“在旧模型上贴新文案”。

## 关键设计决策

- 决策 1：三层唯一正式层级为 `L1_capability / L2_feature / L3_story`。
- 决策 2：目录树保留到 `L3_story`，`Task` 不进入目录。
- 决策 3：`acceptance.yaml` 在 `L1`、`L2_feature` 与 `L3_story` 存在；`Task` 不单独有验收文件。
- 决策 4：测试只保留 `T1~T4` 作为治理语言，不再使用 `L3/L4` 表示测试层。
- 决策 5：`changes/` 旧五层脚手架退出特性树主治理链路。
- 决策 6：任何旧层级、旧兼容字段、旧目录深度在门禁中直接 fail。
- 决策 7：存量中间层若仍有语义价值，迁移为 tag 或元数据，不继续保留目录层。

## 元数据唯一源分层

本特性不是业务 API metadata 设计，而是治理元数据分层设计。

### 唯一真相源

- `specs/feature-tree/tree_index.yaml`
  - 特性树结构唯一索引真相源
- `specs/feature-tree/<L1>/<L2>/spec.md`
  - 规格真相源
- `specs/feature-tree/<L1>/<L2>/design.md`
  - 设计真相源
- `specs/feature-tree/<L1>/<L2>/acceptance.yaml`
  - 验收真相源
- `tasks.md` 或后续 `tasks.yaml`
  - 任务真相源

### 必须移除的第二真相源

- `runtime/tree.yaml` 中的旧四/五层结构
- `changes/feature_catalog.yaml` 与旧 taxonomy
- 脚手架中硬编码的旧 level 枚举
- 测试规则和 deploy 文案中的 `L3/L4` 测试层表达

## TDD / ATDD 策略

本特性本身是治理重构，不是业务功能；因此测试策略以“文档一致性 + 脚本一致性 + 抽样迁移验证”为主。

### ATDD

先以 `acceptance.yaml` 的 A1~A8 作为设计与实施目标：

- 先冻结三层规则
- 再设计切换方案
- 再实施脚本与文档重构
- 最后用 gate 与样例节点验证

### TDD

实施阶段应先补充或更新：

- tree index 生成器测试
- 特性树校验脚本测试
- 旧层级残留扫描测试
- 样例节点迁移验证

再修改对应脚本与文档。

## Story 与测试层映射

本特性自身当前落在 `runtime/development-workflow-governance` 这个治理节点下，后续以其下 `L3_story` 的 Task 作为实施映射：

- 任务 `文档与标准重写`
  - 主要覆盖 `T1`
- 任务 `命令与流程去四层化`
  - 主要覆盖 `T1 + T2`
- 任务 `脚手架、索引和 gate 重写`
  - 主要覆盖 `T1 + T3`
- 任务 `存量节点迁移与抽样验证`
  - 主要覆盖 `T2 + T3`
- 任务 `切换窗口与回滚演练`
  - 主要覆盖 `T3 + T4`

## 角色职责与多重防护网

- **产品/治理 owner**：冻结三层定义，不接受中途回到四层。
- **架构**：定义目录、索引、脚手架和门禁的最终结构。
- **开发**：按任务序列实施文档、脚本、生成器与迁移。
- **测试**：验证 `acceptance.yaml`、`T1~T4`、样例节点迁移和 gate 结果。
- **发布**：控制冻结窗口、合入时机与回滚策略。

多重防护网：

- 规格防偏：`spec.md`
- 方案防漂：`design.md`
- 任务防漏：`tasks.md`
- 验收防回归：`acceptance.yaml`
- 自动化防回长：tree index、脚手架、verify scripts、gate

## 实时性与弱网设计

本特性不涉及实时协议或弱网交互，暂无专项设计要求。

## 并发性能与容量设计

本特性不涉及高并发业务链路，但涉及仓库级批量迁移和 gate 执行时长。需要关注：

- 批量迁移脚本可重复执行
- tree index 重建对全仓目录扫描的稳定性
- 门禁脚本在发现旧层级时应快速失败，避免长时间无效运行

## 灰度发布与回滚设计

这是一次仓库治理切换，不做线上灰度，但需要“治理切换窗口”和“分支级回滚”。

### 切换策略

- 在单独治理分支完成所有文档、脚本、索引和迁移修改
- 切换前冻结新特性创建入口
- 完成 gate 与样例节点验证后一次性合入

### 回滚策略

- 若 tree index 无法稳定重建，回滚整个治理分支
- 若 gate 对旧层级扫描仍有漏网，回滚整个治理分支
- 若样例节点迁移后 `acceptance` 或命令流程不可用，回滚整个治理分支

## 当前态到目标态

### 当前态

- 命令文案默认仍围绕四层/五层运行
- 特性树与测试层使用重复的 `L*` 术语
- 脚手架和索引生成器仍产出旧层级
- `changes/` 与 `specs/feature-tree/` 双轨并存
- 存量 `acceptance.yaml` level 枚举不统一

### 目标态

- 仓库只有一套三层治理语言
- 目录到 `L3_story`
- 测试只用 `T1~T4`
- 脚手架、索引和 gate 对旧层级零容忍
- 所有 `specs/feature-tree/` 节点和验收文件使用同一结构

## 受影响文档与同步边界

本次设计要求覆盖并最终同步以下内容：

- `specs/00_MASTER_DEVELOPMENT_FLOW.md`
- `specs/feature-tree/00_FEATURE_TREE_STANDARD.md`
- `specs/feature-tree/01_FEATURE_TREE_LEVEL_DEFINITIONS.md`
- `.cursor/rules/03-testing.mdc`
- `.cursor/commands/explore.md`
- `.cursor/commands/prd.md`
- `.cursor/commands/design.md`
- `.cursor/commands/dev.md`
- `.cursor/commands/verify.md`
- `.cursor/commands/commit.md`
- `.cursor/commands/deliver.md`
- `.cursor/commands/deploy.md`
- `agent_ops/scaffold/new_feature_fullstack.sh`
- `scripts/verify_feature_traceability.sh`
- `agent_ops/scaffold/verify_feature_tree_refactor.sh`
- `quwoquan_service/runtime/agentpack/tree_index.go`
- `quwoquan_service/tools/gen_tree_index/main.go`
- `specs/feature-tree/tree_index.yaml`
- `specs/feature-tree/runtime/tree.yaml`

## 未来演进

- 为 `Task` 提供结构化 `tasks.yaml`，替代纯 Markdown 清单。
- 给 `/explore`、`/prd`、`/design` 增加结构化输入模版。
- 增加“树迁移审计脚本”，持续防止旧层级回流。

## 存量带规划任务

- `runtime/tree.yaml` 是否彻底废弃，还是只保留三层镜像，需要在实施阶段定稿。
- `changes/` 旧体系退出主治理链路后的保留范围，需要在实施阶段明确。
- 抽样迁移的代表性节点集合，需要在实施阶段确定。
