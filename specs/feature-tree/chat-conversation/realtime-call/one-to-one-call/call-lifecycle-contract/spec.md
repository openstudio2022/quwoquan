# L4 Story：call-lifecycle-contract — 1v1 呼叫状态机契约

> **层级**：L4_story（隶属 L3 `one-to-one-call`）
> **状态**：specified
> **父节点**：`chat-conversation/realtime-call/one-to-one-call`

## 定位

1v1 呼叫状态机契约的可验收交付：定义并实现 CallSession 状态流转（INITIATED→RINGING→CONNECTING→IN_CALL→ENDED）及端云协同行为。

## 职责边界

- 状态机：InitiateCall、AnswerCall、RejectCall、HangupCall、超时 30s 无应答
- 端到端：1v1 语音/视频完整旅程（发起→接听→通话→挂断→记录消息）
- 对应 L2 `realtime-call` acceptance A17~A21、A32~A33

## 与父节点关系

- 父节点 `realtime-call/spec.md` §4.1 CallSession、§4.4 API 端点、§6.2 业务约束
- 父节点 `one-to-one-call/spec.md` 定义 1v1 端到端闭环
- 详细规格与验收标准见 L2 `realtime-call/spec.md` 及 `realtime-call/acceptance.yaml`。
