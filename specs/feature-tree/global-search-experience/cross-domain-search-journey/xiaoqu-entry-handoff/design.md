# xiaoqu-entry-handoff 设计方案

## 设计动因

该 Scenario 保留了历史名字 `xiaoqu-entry-handoff`，但最新 UX 已经把它冻结为独立网络结果页里的 `小趣搜` assistant 结果 tab。设计阶段必须把这次改动严格限制在 `metadata + UI + application + cloud client` 的 typed result 路径上，否则很容易再次退回为 runtime 字符串分流或纯 handoff 占位。

## 最新实现基线（2026-03-22）

以下口径覆盖下文所有历史“问小趣入口”表述：

- `小趣搜` 位于独立网络结果页最左侧 tab，而不是搜索首页快捷入口。
- `小趣搜` 必须返回真实 assistant 摘要、引用与结果强度，不是空跳转。
- 用户可从 `小趣搜` 结果继续打开引用对象，必要时再 continuation 到 assistant 会话。
- `小趣搜` 不单独新增 AI query 历史模型。

## 上游输入评审

| 输入 | 当前结论 |
|---|---|
| `xiaoqu-entry-handoff/spec.md` | 已冻结问小趣是入口而不是结果域 |
| `xiaoqu-entry-handoff/acceptance.yaml` | `A1/S1` 足以承接实施切片 |
| `PERSONAL_ASSISTANT_ARCHITECTURE_AND_FLOW.md` | runtime-thin、metadata-driven、no-fake-answer |
| `PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md` | 设计必须说明影响层、真相源映射、无字符串硬编码、无第二真相源 |

## 对标输入分析

- 对标只吸收“搜索页有一个直接进入智能问答的快捷入口”。
- 不吸收 AI 搜索结果混排。

## 方案对比

### 方案 A：直接把 query 作为页面字符串参数跳到助手页

优点：

- 实现简单。

缺点：

- 没有 typed contract。
- 容易演化成字符串驱动行为。

### 方案 B：单独新增一个 `SearchAi` 接口

优点：

- 语义直观。

缺点：

- 与现有 `assistant_run` 主轴重复。
- 会新增第二套 assistant 真相源。

### 方案 C：复用 `CreateRun / CreateRunStream`，只扩 trigger/context

优点：

- 与 assistant 现有主轴一致。
- 只影响 UI、application 和 cloud client。

缺点：

- 需要在 assistant metadata 中补齐触发来源语义。

## 选型决策

**选定方案：方案 C**

## 关键设计决策

### KD1：影响层冻结为 `UI + application + cloud client`

不改：

- `runtime`
- `skill`
- `tool`
- `prompt`

### KD2：问小趣 handoff 复用 `assistant_run`

建议 contract：

- `CreateRun`
- `CreateRunStream`
- `triggerType = global_search_handoff`
- 可选 source context：
  - `sourceSurfaceId`
  - `sourceQuery`
  - `fromGlobalSearch = true`

### KD3：问小趣 query 生命周期只进入 assistant 对话

- 不进入 recent search
- 不写入搜索结果会话态

### KD4：metadata / codegen 方案

- `assistant/assistant_run/service.yaml`
  - 复用 `CreateRun / CreateRunStream`
- `assistant/_shared/enums.yaml` 或相关 trigger 枚举真相源
  - 新增 `global_search_handoff`
- 必要时在 `assistant/assistant_run/fields.yaml` 增加 handoff context 字段

### KD5：符合性说明

真相源映射：

- assistant 协议：`quwoquan_service/contracts/metadata/assistant/`
- cloud client：`quwoquan_app/lib/cloud/services/assistant/`
- UI 入口：`quwoquan_app/lib/ui/assistant/` 与 global search page

不引入：

- runtime compatibility logic
- skill/tool/phase 新场景文档

原因：

- 本次没有新增 Skill、Tool、Phase，也不是某个 assistant 垂类专项改造，只是入口 handoff。

## 字段演进、迁移/回填、必要时双读双写方案

- 不做双写。
- 若 cloud client 需要短期兼容旧 triggerType，兼容逻辑仅允许存在于 client 参数适配层，并以 dev 完成后删除为退出条件。

## feature flag、观测、SLO 验证与回滚方案

- 无业务 feature flag。
- 观测：
  - `xiaoqu_handoff_count`
  - `xiaoqu_handoff_success_count`
  - `xiaoqu_handoff_failure_count`
  - `xiaoqu_handoff_empty_query_count`
- SLO：
  - handoff `P95 < 800ms`
- 回滚：
  - 整版回退，不新增 AI 混排兜底

## TDD / ATDD 策略

- `T1_schema`：assistant trigger / handoff context contract
- `T2_module_interaction`：问小趣入口与页面跳转
- `T3_cross_service_integration`：assistant run 创建与会话接续
- `T4_user_journey`：从搜索页进入问小趣对话

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 主要证据 |
|---|---|---|
| `P1` | 冻结 assistant handoff trigger/context contract | `T1_schema` |
| `P2` | 落地搜索页入口、参数组装与 cloud client 调用 | `T2_module_interaction`, `T3_cross_service_integration` |
| `P3` | 验证 assistant 会话接续与无字符串路由 | `T2_module_interaction`, `T4_user_journey` |

## 未来演进

- 若后续需要更丰富的来源上下文，只扩展 typed handoff context，不新增第二套搜索 AI 接口。
