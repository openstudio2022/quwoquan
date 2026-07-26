# L2 Design：设置、设备与账号安全 (`settings-and-device-token`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“为已登录账号提供可真实读写的通知、隐私、通话、外观设置，管理设备推送端点与登录凭证，”需要 `account-lifecycle-self-service-account-closure`、`account-suspension-and-appeal-lifecycle`、`appearance-accessibility-settings`、`device-token-register`、`notification-privacy-settings`、`settings-audit` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：为已登录账号提供可真实读写的通知、隐私、通话、外观设置，管理设备推送端点与登录凭证。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`account-lifecycle-self-service-account-closure`](./account-lifecycle-self-service-account-closure/spec.md)：真实事务存储证明状态、receipt 与 outbox 同提交，并发提交只产生一个终态事实。
- [`account-suspension-and-appeal-lifecycle`](./account-suspension-and-appeal-lifecycle/spec.md)：真实存储事务证明状态、epoch、session revoke 与 outbox 同提交，且没有 PII/审核证据进入事件。
- [`appearance-accessibility-settings`](./appearance-accessibility-settings/spec.md)：必须挂在 `settings-and-device-token` 下，以 metadata / API / audit 为真相源，禁止做成仅本地存储能力。
- [`device-token-register`](./device-token-register/spec.md)：定义“设备 Token 登记”的可观察主路径、失败语义及父能力交接。
- [`notification-privacy-settings`](./notification-privacy-settings/spec.md)：定义“通知隐私设置”的可观察主路径、失败语义及父能力交接。
- [`settings-audit`](./settings-audit/spec.md)：定义“设置审计”的可观察主路径、失败语义及父能力交接。

## 3. 端云与数据流

- 上游能力：[`user-identity-profile-relationship`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 设置命令与设备令牌写入各自 owner 并返回结构化终态
- 决策：设置命令与设备令牌写入各自 owner 并返回结构化终态。
- 理由：为已登录账号提供可真实读写的通知、隐私、通话、外观设置，管理设备推送端点与登录凭证。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`account-lifecycle-self-service-account-closure`](./account-lifecycle-self-service-account-closure/spec.md)、[`account-suspension-and-appeal-lifecycle`](./account-suspension-and-appeal-lifecycle/spec.md)、[`appearance-accessibility-settings`](./appearance-accessibility-settings/spec.md)、[`device-token-register`](./device-token-register/spec.md)、[`notification-privacy-settings`](./notification-privacy-settings/spec.md)、[`settings-audit`](./settings-audit/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 UserAccount 是所有终端用户请求的同步安全权威
- 决策：资源服务只在 `JWT` 验签成功后调用 `UserAccount` service-principal internal operation。
- 权威返回：该 operation 只返回 `accountState` 与 `authEpoch`，响应 `Cache-Control: no-store`，不返回或记录 persona、资料、凭证、设备、case 或原始事件。
- 同步拒绝：资源中间件仅在 active/anonymous 且 token epoch 精确匹配时注入 principal；closed、suspended、not found 和 stale 以 canonical `USER.AUTH.*` 拒绝，任何 authority 依赖失败一律 fail-closed。
- 理由：签名验证只能证明 token 曾被签发，不能证明注销、封禁或 epoch 变更后的当前终态。把用户安全终态放在每个服务的本地 cache、JWT TTL 或异步 consumer 会制造可访问窗口和第二真相源。
- 新动作校验：HTTP 同步校验负责新动作；realtime gateway 的 ticket/upgrade/connection 和 RTC 的 join/renewal 同样调用 authority。
- 既有连接回收：`UserAccountClosed`/`UserSuspended` durable event 负责主动踢除已建立连接、presence、lease、ticket、CallSession 与 media access；事件是回收机制而不是新请求鉴权的替代。
- 可靠性与隐私：authority、outbox relay 和各 consumer 均采用 bounded retry、无 PII terminal DLQ、可恢复 replay 与 readiness。DLQ 只保存不可逆 event/reference/error digest，原 payload 从未 ACK 的 durable source 恢复。Content 对媒体使用引用安全的 revoke/GC work 和 residual probe，不能因为 metadata 已删除就假定 CAS/public slice 已清除。
- 被否决方案：仅缩短 JWT/ticket TTL。
- 被否决方案：仅依赖 UserAccountClosed 异步事件。
- 被否决方案：资源服务缓存 active 快照。
- 被否决方案：authority 不可用时沿用上次成功结果。
- 被否决方案：让 DLQ 保存 account/persona/raw payload。
- 被否决方案：由页面或 App 决定旧 token 是否失效。
- 约束与影响：authority client 必须用受限服务身份、显式 internal origin、短超时、no-store 和无 PII telemetry；生产装配缺少 URL、凭据、timeout 或 health 时 fail-fast。唯一 closed 放行是 canonical CloseAccount 的幂等重放，且由 UserAccount 自身在已确认终态后处理。所有新服务调用只能通过公开 internal contract，不得 import UserAccount infrastructure。
- 关联要求：`REQ-003`、`REQ-004`
- 关联验收：`SIT-003`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 并观测 outbox/consumer/DLQ 指标；封禁旅程额外验证旧 token 拒绝、受限主页不可见、申诉。
- Suspend/Restore 各一次、验证 epoch 拒绝与下游 lag/DLQ 告警。
- authority 观测至少包含固定 outcome 的 allow/closed/suspended/stale/unavailable、延迟和 readiness；不允许用 account、persona、token、request payload 作为 metric label 或日志字段。
