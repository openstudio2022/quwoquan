# L2 特性：runtime-messaging

## 功能说明
- 提供异步消息运行时语义层：envelope、schema、幂等、重试、死信与重放。
- 统一生产与消费端行为，支持 trace/parentTrace/causation 全链路传播。

## 约束
- 消息 envelope 必须对齐 `contracts/messages/envelope.schema.json`。
- 业务服务不得直接拼装消息结构与重试策略，必须复用 runtime-messaging。
- 消费端必须支持幂等，避免重复副作用。

## 验收标准
- A1：统一生产/消费 API 可直接接入服务。
- A3：重试、死信、重放策略可配置可追踪。
- A7：envelope 与 schema 契约一致。
- A8：消息语义自动化测试完整。
