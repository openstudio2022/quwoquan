# L2 Business Capability：设置、设备与账号安全 (`settings-and-device-token`)

> 所属领域：[`user-identity-profile-relationship`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

让已登录用户真实读取和修改通知、隐私、通话与外观设置，并安全管理设备推送端点、账号处置和登录凭证。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“L2 业务能力：设置、设备与账号安全”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-004`](../../spec.md#scn-004)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：为已登录账号提供可真实读写的通知、隐私、通话、外观设置，管理设备推送端点与登录凭证，，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`account-lifecycle-self-service-account-closure`](./account-lifecycle-self-service-account-closure/spec.md)：真实事务存储证明状态、receipt 与 outbox 同提交，并发提交只产生一个终态事实。
- [`account-suspension-and-appeal-lifecycle`](./account-suspension-and-appeal-lifecycle/spec.md)：真实存储事务证明状态、epoch、session revoke 与 outbox 同提交，且没有 PII/审核证据进入事件。
- [`appearance-accessibility-settings`](./appearance-accessibility-settings/spec.md)：必须挂在 `settings-and-device-token` 下，以 metadata / API / audit 为真相源，禁止做成仅本地存储能力。
- [`device-token-register`](./device-token-register/spec.md)：定义“设备 Token 登记”的可观察主路径、失败语义及父能力交接。
- [`notification-privacy-settings`](./notification-privacy-settings/spec.md)：定义“通知隐私设置”的可观察主路径、失败语义及父能力交接。
- [`settings-audit`](./settings-audit/spec.md)：定义“设置审计”的可观察主路径、失败语义及父能力交接。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 settings and device token 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“为已登录账号提供可真实读写的通知、隐私、通话、外观设置，管理设备推送端点与登录凭证，”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 账号封禁、恢复与申诉可逆处置 SIT

- Product Ops 受信 decision 驱动 UserAccount active↔suspended；closed 账号永不允许恢复。
- Suspend 原子递增 auth epoch、撤销 session/refresh，认证与服务鉴权拒绝 suspended 或旧 epoch token。
- Content、Chat、Circle、Notification、Search 与 Recommendation 以可逆 restriction projection 收敛，Restore 不复用注销删除器。
- moderation/appeal workflow、审批链、case/ref/request/trace/evidence audit 和 retry/DLQ 可审计。

<a id="req-003"></a>
### REQ-003 账号注销进入不可逆 closed 终态

- 用户二次确认注销后，`UserAccount` 必须原子进入不可逆 `closed` 终态，并吊销全部 session、refresh token 与有效设备凭据。
- 数据导出与撤回同意由独立的数据主体权利 Story 负责，不属于本能力范围。
- 已注销账号不得恢复；本能力不提供冷静期或撤销双轨。
- 指标必须覆盖设置写失败、设备端点失败、注销 outbox 失败和各下游消费重试/DLQ。
- 受信 Suspend/Restore 决策、申诉审批、closed 不可恢复、会话撤销和 auth epoch 必须形成可审计链路。

<a id="req-004"></a>
### REQ-004 全服务同步账号安全权威 SIT

- 任一资源服务在验签成功后、将 principal 注入业务请求前，必须向 `UserAccount` 的最小同步权威读取 `accountState` 与 `authEpoch`。
- `closed`、`suspended`、账号不存在和 epoch 不匹配必须在同一请求内返回 canonical `USER.AUTH.account_deleted`、`USER.AUTH.account_suspended` 或 `USER.AUTH.token_stale`；权威超时、网络失败、无效响应、未配置或未通过 readiness 时必须返回 `USER.AUTH.account_security_unavailable`，不得沿用缓存或放行。
- service/operator/device principal 与 public 请求不被当作终端用户账号校验；唯一例外是 metadata 明确的 closed `CloseAccount` 幂等重放，且只能在已确认 closed 后放行。
- WS ticket、连接升级、RTC join/renewal 也必须读取同一权威；`UserAccountClosed` 与 `UserSuspended` durable event 必须主动收回既有 WS、presence、lease、ticket、CallSession 与 media room access。
- authority、outbox、consumer、DLQ、WS/RTC eviction 的指标、trace 与日志字段不得包含 accountId、personaId、token 或原始 payload。

## 6. 契约与依赖

- 上游能力：[`user-identity-profile-relationship`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 settings and device token 能力 SIT

- GIVEN 执行“settings and device token 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“settings and device token 能力”对应动作。
- THEN 直属 Story 共同交付“为已登录账号提供可真实读写的通知、隐私、通话、外观设置，管理设备推送端点与登录凭证，”，失败终态可区分且不产生伪成功事实。

<a id="sit-002"></a>
### SIT-002 账号封禁、恢复与申诉可逆处置 SIT

- GIVEN 执行“账号封禁、恢复与申诉可逆处置”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“账号封禁、恢复与申诉可逆处置”对应动作。
- THEN Product Ops 受信 decision 驱动 UserAccount active↔suspended；closed 账号永不允许恢复。
- THEN Suspend 原子递增 auth epoch、撤销 session/refresh，认证与服务鉴权拒绝 suspended 或旧 epoch token。
- THEN Content、Chat、Circle、Notification、Search 与 Recommendation 以可逆 restriction projection 收敛，Restore 不复用注销删除器。
- THEN moderation/appeal workflow、审批链、case/ref/request/trace/evidence audit 和 retry/DLQ 可审计。

<a id="sit-003"></a>
### SIT-003 全服务同步账号安全权威

- GIVEN 用户 access JWT 曾在 active epoch 签发，且任意资源服务、WS gateway 或 RTC 已准备接受该主体。
- WHEN UserAccount 原子变为 closed 或 suspended，或者 authority 返回 epoch 不匹配、账号不存在或不可用。
- THEN 每个新的 HTTP/WS/RTC 受保护动作在业务入口前被正确拒绝；authority 不可用绝不放行。
- THEN 已存在 WS、presence、lease、ticket、CallSession、media room access 由 durable 终态事件幂等回收，重复事件、重试和跨节点消费不产生残留或重复结束事实。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 settings and device token 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：为已登录账号提供可真实读写的通知、隐私、通话、外观设置，管理设备推送端点与登录凭证。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 账号封禁、恢复与申诉可逆处置 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：Product Ops 受信 decision 驱动 UserAccount active↔suspended；closed 账号永不允许恢复。
- 完成判定：`SIT-002` 对应行为满足且真实测试 `spec_ref` 有效
