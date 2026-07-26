# L3 Story：运行流式协议 (`run-stream-protocol`)

> 所属能力：[`run-stream-policy`](../spec.md)

> Journey / Scenario：[`JNY-009 / SCN-017`](../../../spec.md#scn-017)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为使用小趣的用户或助手运营者，
我希望`run_started` 后先以 `process_replace` 建立过程快照；同一 run 的 `seq` 严格递增且唯一，
从而获得可解释、可恢复且可持续改进的助手结果。

## 2. 范围与非目标

### In Scope

- “运行流式协议”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 运行流式协议

- `run_started` 后先以 `process_replace` 建立过程快照；同一 run 的 `seq` 严格递增且唯一。

<a id="req-002"></a>
### REQ-002 事件顺序与首个可见回答观测

- `run_started` 后必须先以 `process_replace` 建立过程快照；同一 run 的 `seq` 必须严格递增且唯一。
- 首个 `answer_delta` 必须写入 `assistant_first_visible_response_ms`，用于观测首个可见回答延迟。
- 未知事件类型、内部字段泄露、缺失或多重终态均按契约失败，不得静默降级。

<a id="req-003"></a>
### REQ-003 禁止直接驱动用户可见过程文案、最终答案文本或动效分支

- **禁止**直接驱动用户可见过程文案、最终答案文本或动效分支。
- 每个事件必须携带 `schema`、`eventId`、`conversationId`、`turnId`、`seq`、`eventType` 与 `createdAt`；不得另造未声明的 `scope` 字段。
- 过程事件正文必须使用用户语言，围绕“已经为你做了什么 / 正在为你核对什么”表达，禁止携带内部推理、prompt、credential 或 secret。
- `answer_delta` 不得复用于过程抽屉，也不得被 `process_*` 事件反向回填。
- completed 终态必须携带可展示 answer 或可重放的结构化 journey 之一。
- 必须携带终态 `AssistantJourney` 或足以重放出同构 `AssistantJourney` 的结构化数据。
- terminal payload 缺失时，只允许在“已确认具备完整 answer 通道内容”时合成 completed；否则必须回退到非流式 run 或显式不完整失败，不得用过程文本强行封箱。
- `process_*` 可在 `answer_delta` 之前或期间继续推进，但不得把过程文本并入答案缓冲。
- `trace` 可与任何事件交错，但不得改变用户态 reducer 的最终结果。
- 无真实 `journey` 内容时不得因为 seeded stages 而默认显示过程抽屉。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 运行流式协议

- GIVEN 使用小趣的用户或助手运营者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“运行流式协议”对应的公开行为。
- THEN `run_started` 后必须先以 `process_replace` 建立过程快照；同一 run 的 `seq` 严格递增且唯一。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`run-stream-policy`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
