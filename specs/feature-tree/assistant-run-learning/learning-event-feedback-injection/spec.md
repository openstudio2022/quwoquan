# L2 Business Capability：学习事件反馈注入 (`learning-event-feedback-injection`)

> 所属领域：[`assistant-run-learning`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

统一学习事件上报、反馈聚合与运行时上下文注入链路。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“learning-event-feedback-injection”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-007 / SCN-015`](../../spec.md#scn-015)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：统一学习事件上报、反馈聚合与运行时上下文注入链路。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`feedback-aggregation`](./feedback-aggregation/spec.md)：定义“反馈聚合”的可观察主路径、失败语义及父能力交接。
- [`feedback-context-injection`](./feedback-context-injection/spec.md)：定义“反馈上下文注入”的可观察主路径、失败语义及父能力交接。
- [`learning-event-ingestion`](./learning-event-ingestion/spec.md)：`queryTextDigest`（不得直接以原始敏感文本进入公开分析层）。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 学习事件反馈注入能力组合结果

- 本能力必须组合直属 Story 与公开契约，交付“统一学习事件上报、反馈聚合与运行时上下文注入链路”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 统一学习事件上报、反馈聚合与运行时上下文注入链路

- 统一学习事件上报、反馈聚合与运行时上下文注入链路。
- `AppendAssistantLearningFact` 必须是用户反馈、交互结果与服务评分唯一的 append command；`eventId` 定义幂等身份，`payloadDigest` 检测同身份冲突，服务端 `appendSequence` 定义唯一追加顺序，不保留旧 wire 或双轨上报。
- 反馈注入只能读取通过策略校验的数据，不得直接拼接原始未校验字段。
- `learning-event-ingestion`：统一学习事实追加、落库标准、与统一事件体系桥接
- 通过 `product-ops-growth/event-ingestion-and-analytics` 共享统一事件字典、schema 治理、实验与分析维度

## 6. 契约与依赖

- 上游能力：[`assistant-run-learning`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 learning event feedback injection 能力 SIT

- GIVEN 执行“learning event feedback injection 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“learning event feedback injection 能力”对应动作。
- THEN 直属 Story 共同交付“统一学习事件上报、反馈聚合与运行时上下文注入链路”，失败终态可区分且不产生伪成功事实。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 learning event feedback injection 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺可用 Gamma Remote 与 Prod 获批 Provider conformance、发布回执；三条代码链路已由 `AssistantLearningFact` append sink、canonical-definition projection 和 policy-filtered feedback context 收敛，local/API 合同已直连 Story `spec_ref`，但 gamma-local health gate 当前为 0/28，未取得当前真实 append、幂等 receipt 与 durable relay 回读，且不得在生产环境执行破坏性学习事实探针。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效，并在可用 alpha/beta/gamma/prod 环境中复验。
