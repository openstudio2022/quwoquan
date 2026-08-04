# L2 Business Capability：助手运行时基础 (`assistant-runtime-foundation`)

> 所属领域：[`assistant-run-learning`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

承载助手域业务对象运行基座：`AssistantSession`/`AssistantTurn` 会话与轮次持久化、`SkillSubscription` 主动订阅、`SkillConsent` 敏感能力授权门控、入口个性化与个人数据查询。

## 2. 范围与非目标

### In Scope

- AssistantSession/AssistantRun 对象 Store（state/receipt/outbox）与重启恢复语义
- SkillSubscription receipts/outbox 与 cron lease 领取
- SkillConsent 版本化事实、执行点 fail-closed 门控与事件
- 端侧对象级 Remote Facet、local_contract typed double 物理隔离、结构化错误单轨

### Out of Scope

- Run/Stream 协议与策略模板（归 run-stream-policy）
- 学习事件聚合与反馈注入（归 learning-event-feedback-injection）

## 3. Journey / Scenario 贡献

- [`JNY-007 / SCN-015`](../../spec.md#scn-015)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：承载助手域业务对象运行基座：`AssistantSession`/`AssistantTurn` 会话与轮次持久化、`SkillSubscription` 主动订阅、`SkillConsent` 敏感能力授权门控、入口个性化与个人数据查询，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-009 / SCN-017`](../../spec.md#scn-017)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：承载助手域业务对象运行基座：`AssistantSession`/`AssistantTurn` 会话与轮次持久化、`SkillSubscription` 主动订阅、`SkillConsent` 敏感能力授权门控、入口个性化与个人数据查询，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-009 / SCN-018`](../../spec.md#scn-018)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：承载助手域业务对象运行基座：`AssistantSession`/`AssistantTurn` 会话与轮次持久化、`SkillSubscription` 主动订阅、`SkillConsent` 敏感能力授权门控、入口个性化与个人数据查询，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-009 / SCN-019`](../../spec.md#scn-019)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：承载助手域业务对象运行基座：`AssistantSession`/`AssistantTurn` 会话与轮次持久化、`SkillSubscription` 主动订阅、`SkillConsent` 敏感能力授权门控、入口个性化与个人数据查询，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-009 / SCN-020`](../../spec.md#scn-020)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：承载助手域业务对象运行基座：`AssistantSession`/`AssistantTurn` 会话与轮次持久化、`SkillSubscription` 主动订阅、`SkillConsent` 敏感能力授权门控、入口个性化与个人数据查询，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story

- [`assistant-object-runtime`](./assistant-object-runtime/spec.md)：服务重启后必须能按 owner 读取会话与运行；敏感操作在 consent 缺失、撤销或存储不可用时必须拒绝执行。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 助手对象运行基座能力 SIT

- `AssistantSession`/`AssistantRun`/`AssistantTurn` 状态持久化于 MongoDB 对象 Store
- 服务重启后 run 可读、SSE resume 语义明确
- 进程内业务状态 map 为零。
- 创建类命令以稳定 intent + 唯一约束 + receipt 幂等
- 状态迁移类命令服务端内部 CAS + no-op receipt
- 公开请求无调用方版本字段。
- cron/主动投递经带 TTL 的 lease 领取，多实例并发不重复投递。
- consent 在敏感能力执行点强制校验且 fail-closed；未授权、撤权后、伪造身份、store 不可用负例全部拒绝。
- 端侧经对象级 Facet 消费，production 无 mock 可达、无吞异常 fallback、无本地合成成功数据。
- 对话/half sheet/技能中心/管理页消费真实 Facet；错误可见可恢复，任务/记忆具备 loading/empty/error/data 四态，无本地假开关、演示订阅载荷或悬空双写路径。

<a id="req-002"></a>
### REQ-002 AssistantSession/AssistantTurn 状态必须持久化于对象专属 Store（MongoDB `assistant_sessions`/`assistant_runs`），服务重启后 run 可读、SSE resume 语义明确

- `AssistantSession`/`AssistantTurn` 状态必须持久化于对象专属 Store（MongoDB `assistant_sessions`/`assistant_runs`），服务重启后 run 可读、SSE resume 语义明确；禁止进程内 map 承载业务状态。
- Assistant 聚合 identity 只使用 `sessionId`；`X-Client-Session-Id` 代表 App 启动会话，只能归一化为内部审计字段 `clientSessionId`，不得与 `AssistantSession.sessionId` 混用。
- 会话生命周期必须提供 owner 隔离的会话分页、终态轮次分页、Run 查询和取消命令；取消以 running → cancelled CAS 收口，重复取消对终态幂等。
- 生产启动只能注入 MongoDB 会话/Run Store；内存 Store 仅允许在测试装配中使用。
- cron/主动投递的领取必须用带 TTL 的 lease（`acquireDueLeases` 语义），禁止内存 claim；多实例可安全并发。
- 端侧只经对象级 typed Facet 消费；不可用状态以结构化 `RuntimeFailure` 呈现，禁止本地合成成功数据或假兜底。
- App 历史初始化或会话切换失败时必须展示结构化错误并可重试；在恢复成功前不得把失败当作空历史并暗中新建会话。
- consent 负例（未授权、撤权后、伪造身份、store 不可用）全部 fail-closed。

## 6. 契约与依赖

- 上游能力：[`assistant-run-learning`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 助手对象运行基座能力 SIT

- GIVEN 执行“助手对象运行基座能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“助手对象运行基座能力”对应动作。
- THEN `AssistantSession`/`AssistantRun`/`AssistantTurn` 状态持久化于 MongoDB 对象 Store
- AND 服务重启后 run 可读、SSE resume 语义明确
- AND 进程内业务状态 map 为零。
- THEN 会话与终态轮次按 owner 隔离分页，Run 可查询与取消，重复取消不改写已有终态；新服务实例仍能从 MongoDB 读取取消结果。
- THEN 创建类命令以稳定 intent + 唯一约束 + receipt 幂等
- AND 状态迁移类命令服务端内部 CAS + no-op receipt
- AND 公开请求无调用方版本字段。
- THEN cron/主动投递经带 TTL 的 lease 领取，多实例并发不重复投递。
- THEN consent 在敏感能力执行点强制校验且 fail-closed；未授权、撤权后、伪造身份、store 不可用负例全部拒绝。
- THEN 端侧经对象级 Facet 消费，production 无 mock 可达、无吞异常 fallback、无本地合成成功数据。
- THEN 对话/half sheet/技能中心/管理页消费真实 Facet；错误可见可恢复，任务/记忆具备 loading/empty/error/data 四态，无本地假开关、演示订阅载荷或悬空双写路径。
- THEN 历史恢复失败显示结构化错误与重试，且失败未恢复时不发起新会话。

## 8. 开放事项

<a id="open-003"></a>
### OPEN-003 助手手写运行对象仍未完成 metadata/codegen 类型化

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺的实现与验收证据是 `RunItem.payload`、trigger/context/surface/presentation 内部快照及 planner/observation/tool retrieval/orchestration 的匿名 Map/`dynamic` 收敛，以及这些类型在真实后台恢复、重放与压缩链路中的同结构证明；metadata-owned `AssistantRunTerminalSnapshotView` 已以无 TTL owner 存储持久化 answer、可见 process/citation、failure 与 selected policy，GetRun、历史恢复和 journal 过期后的 SSE 终态重放已共用该事实，但长任务中间过程仍无法获得与终态同等级的字段安全证明。
- 完成判定：按 `run artifacts -> turn protocol -> planner/observation -> tool retrieval -> orchestration` 将剩余弱类型数据收敛为 metadata-owned 具名 DTO/sealed type，并由持久化/重放/压缩使用同一结构；弱类型棘轮只减不增，禁止另建兼容 decoder 或第二 projection。
- 依赖：assistant metadata schema 与 app codegen。

<a id="open-004"></a>
### OPEN-004 assistant_run 聚合仍承载多类互不相关的能力

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 task、page context、entry personalization、creation assistance 与 search facade 的独立对象、source/store 和三层验收归属，这些能力仍混在 `assistant_session` 编排服务，且 `ReportPageContext` 在无 run 时也会调用。`assistant_turn_view` 已拥有独立 operations、HTTP Route、QueryFacade、Mongo Reader 与响应 Slice，`AssistantSession` 聚合服务和 `SessionRunStore` 已删除 turn 列表能力，local_contract 与真实 Mongo/Redis/Postgres API integration 已通过，但候选绑定的四环境 Remote UAT、SLI/SLO 与回滚证据尚缺。聚合根裸对象硬门已经建立，旧 `assistant_run` 根上 14 个未进入真实 Mongo `AssistantTurn` 的万能 payload 字段已删除。技能目录已由 `assistant.skill_catalog` 单轨拥有，`GetLearningOpsSummary` 与 `AssistantLearningOpsSummaryView` 已由 `assistant_learning_fact` 单轨拥有。
- 完成判定：把 task、入口态与检索门面拆出聚合。`assistant_turn_view` 持续作为 turn 唯一读侧，每个拆出对象都具有独立 contract、application facade、source/store 归属与三层证据。`verify_metadata` 持续断言 `kind: aggregate_root` 的根字段不得为裸 `object`/`[]object`，临时 Post allowlist 只减不增且清零后删除。
- 依赖：`quwoquan_service/tools/verify_metadata`。
