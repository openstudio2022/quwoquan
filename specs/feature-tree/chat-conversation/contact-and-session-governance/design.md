# L2 Design：联系人与会话治理 (`contact-and-session-governance`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“以“关注”为唯一关系概念，验证关注状态、拉黑门禁、打招呼请求箱、正式私信与 1v1 RTC 的端云一致性”需要 `conversation-entry-matrix`、`greeting-request-inbox-and-upgrade`、`session-audit-observability`、`session-governance-actions` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：以“关注”为唯一关系概念，验证关注状态、拉黑门禁、打招呼请求箱、正式私信与 1v1 RTC 的端云一致性。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`conversation-entry-matrix`](./conversation-entry-matrix/spec.md)：拉黑级联与三处服务端门禁均有真实存储/API 证据。
- [`greeting-request-inbox-and-upgrade`](./greeting-request-inbox-and-upgrade/spec.md)：会话升级、幂等与关注状态不变均有 API 集成证据。
- [`session-audit-observability`](./session-audit-observability/spec.md)：定义“会话审计可观测性”的可观察主路径、失败语义及父能力交接。
- [`session-governance-actions`](./session-governance-actions/spec.md)：定义“会话治理动作”的可观察主路径、失败语义及父能力交接。

## 3. 端云与数据流

- 上游能力：[`chat-conversation`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- canonical 引用：`quwoquan_service/contracts/metadata/_shared/types.yaml#RelationshipState`、`quwoquan_service/services/user-service/contracts/relationship/subject_follow/operations.yaml`、`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/operations.yaml`、`quwoquan_service/services/user-service/contracts/relationship/greeting_request/operations.yaml`、`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml#CreateConversation`、`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml#SendMessage`
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 关注、打招呼、正式会话与拉黑使用独立状态边界
- 决策：关注、打招呼、正式会话与拉黑使用独立状态边界。
- 理由：以“关注”为唯一关系概念，验证关注状态、拉黑门禁、打招呼请求箱、正式私信与 1v1 RTC 的端云一致性。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`conversation-entry-matrix`](./conversation-entry-matrix/spec.md)、[`greeting-request-inbox-and-upgrade`](./greeting-request-inbox-and-upgrade/spec.md)、[`session-audit-observability`](./session-audit-observability/spec.md)、[`session-governance-actions`](./session-governance-actions/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 沿用父 L1 质量约束；新增特有 SLO 时在本节声明。
