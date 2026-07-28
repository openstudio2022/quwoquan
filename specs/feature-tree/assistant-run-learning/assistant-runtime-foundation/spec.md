# L2 Business Capability：助手运行时基础 (`assistant-runtime-foundation`)

> 所属领域：[`assistant-run-learning`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

承载助手域业务对象运行基座：`AssistantConversation`/`AssistantTurn` 会话与轮次持久化、`SkillSubscription` 主动订阅、`SkillConsent` 敏感能力授权门控、入口个性化与个人数据查询。

## 2. 范围与非目标

### In Scope

- AssistantConversation/AssistantRun 对象 Store（state/receipt/outbox）与重启恢复语义
- SkillSubscription receipts/outbox 与 cron lease 领取
- SkillConsent 版本化事实、执行点 fail-closed 门控与事件
- 端侧对象级 Remote Facet、local_contract typed double 物理隔离、结构化错误单轨

### Out of Scope

- Run/Stream 协议与策略模板（归 run-stream-policy）
- 学习事件聚合与反馈注入（归 learning-event-feedback-injection）

## 3. Journey / Scenario 贡献

- [`JNY-007 / SCN-015`](../../spec.md#scn-015)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：承载助手域业务对象运行基座：`AssistantConversation`/`AssistantTurn` 会话与轮次持久化、`SkillSubscription` 主动订阅、`SkillConsent` 敏感能力授权门控、入口个性化与个人数据查询，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-009 / SCN-017`](../../spec.md#scn-017)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：承载助手域业务对象运行基座：`AssistantConversation`/`AssistantTurn` 会话与轮次持久化、`SkillSubscription` 主动订阅、`SkillConsent` 敏感能力授权门控、入口个性化与个人数据查询，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-009 / SCN-018`](../../spec.md#scn-018)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：承载助手域业务对象运行基座：`AssistantConversation`/`AssistantTurn` 会话与轮次持久化、`SkillSubscription` 主动订阅、`SkillConsent` 敏感能力授权门控、入口个性化与个人数据查询，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-009 / SCN-019`](../../spec.md#scn-019)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：承载助手域业务对象运行基座：`AssistantConversation`/`AssistantTurn` 会话与轮次持久化、`SkillSubscription` 主动订阅、`SkillConsent` 敏感能力授权门控、入口个性化与个人数据查询，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-009 / SCN-020`](../../spec.md#scn-020)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：承载助手域业务对象运行基座：`AssistantConversation`/`AssistantTurn` 会话与轮次持久化、`SkillSubscription` 主动订阅、`SkillConsent` 敏感能力授权门控、入口个性化与个人数据查询，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`assistant-object-runtime`](./assistant-object-runtime/spec.md)：服务重启后必须能按 owner 读取会话与运行；敏感操作在 consent 缺失、撤销或存储不可用时必须拒绝执行。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 助手对象运行基座能力 SIT

- conversation/run/turn 状态持久化于 MongoDB 对象 Store
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
### REQ-002 conversation/turn 状态必须持久化于对象专属 Store（MongoDB `assistant_conversations`/`assistant_runs`），服务重启后 run 可读、SSE resume 语义明确

- conversation/turn 状态必须持久化于对象专属 Store（MongoDB `assistant_conversations`/`assistant_runs`），服务重启后 run 可读、SSE resume 语义明确；禁止进程内 map 承载业务状态。
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
- THEN conversation/run/turn 状态持久化于 MongoDB 对象 Store
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
- 影响或价值：仍缺 metadata/codegen 类型化。公开 Run 已收敛为 metadata-owned `AssistantTurnEnvelope`，内部 request context 不再越过 HTTP，但终态只持久化文本/失败，`run artifacts`、stream payload、planner/observation、tool retrieval 与 orchestration 仍有匿名 Map/`dynamic`，无法在 journal TTL 后可靠恢复结构化过程或证明字段安全。
- 完成判定：先定义并持久化 metadata-owned terminal snapshot（answer、可见 process/citation、failure、selected policy）。随后按 `run artifacts -> turn protocol -> planner/observation -> tool retrieval -> orchestration` 收敛为具名 DTO/sealed type。GetRun/历史恢复与 SSE 使用同一 projection，弱类型棘轮只减不增。
- 依赖：assistant metadata schema 与 app codegen。
