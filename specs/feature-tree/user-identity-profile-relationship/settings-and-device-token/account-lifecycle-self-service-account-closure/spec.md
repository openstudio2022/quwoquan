# L3 Story：自助账号注销 (`account-lifecycle-self-service-account-closure`)

> 所属能力：[`settings-and-device-token`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理账号、Persona 或关系的用户，我希望验证账号注销的 owner 命令、原子清理、跨域收敛与用户安全落点，从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- CloseAccount 鉴权、幂等、并发串行化和 closed 终态。
- 用户域会话、凭证、Persona、PII/SECRET 原子清理与 durable outbox。
- 跨域匿名化/删除消费者、重试、无 PII DLQ、监控与 App 成功/失败体验。
- App 在云侧终态成功后清除本地凭据、待投递队列、未发布草稿、身份隔离缓存及 push/来电秘密状态。
- 资源服务同步账号安全权威拒绝、WS/RTC 主动回收，以及媒体对象引用安全 revoke/GC residual probe。

### Out of Scope

- 冷静期、撤销注销与旧账号恢复。
- 数据导出、撤回同意和法定留存政策制定。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 owner 注销原子成功且重放返回稳定终态

- 真实事务存储证明状态、receipt 与 outbox 同提交，并发提交只产生一个终态事实。

<a id="req-002"></a>
### REQ-002 越权或事务失败不产生部分注销

- 越权、存储失败和 outbox 写入失败均有 rollback 证据。

<a id="req-003"></a>
### REQ-003 跨域最终清理并回到游客安全态

- Gamma/Prod 真机 UAT、旧 token 拒绝、下游清理探针、DLQ 与排空演练均有制品。
- authenticated owner 只能从 canonical `settings.account_security` 的明确确认动作经 production Remote 提交注销；取消确认不得发出命令，canonical failure 必须保留当前会话、页面与可重试入口，只有 typed `closed` 终态才可启动本地终态清理并返回游客安全首页。
- App 必须在清除凭据前持久化加密本地清理回执，读回确认本地凭据、队列、草稿、账号关联缓存与 push/来电秘密状态无残留后才删除回执；进程崩溃或其他设备注销后收到 canonical `account_deleted` 时必须在启动链路幂等恢复清理。
- 本地清理异常不能恢复已关闭会话；失败回执必须保留并重试，禁止以仅记录日志代替最终清理。

<a id="req-004"></a>
### REQ-004 清理结果不可逆匿名化且具备无 PII 可观测与残留阻断

- 法定留存期限由所属合规政策另行决定；任何实际保留事实必须不可逆匿名化且不能用于重新识别。
- outbox 失败率、消费者重试/DLQ 和清理延迟必须可观测；日志与 metric label 禁止 PII。
- 推荐清理必须有 Mongo、Redis、内存、training 与 replay residual probe；任一 probe 非零或缺失都必须阻断注销清理准出。
- Prod 环境证据必须包含真机流程、旧 token 拒绝、下游清理探针和回滚/排空演练。

<a id="req-005"></a>
### REQ-005 注销提交后所有入口立即失效且既有长连接被回收

- 同一旧 access JWT 在任意资源服务新请求中都必须同步得到 `USER.AUTH.account_deleted`；不能依赖 JWT、refresh token 或 ticket 的自然过期。
- authority 不可用得到 `USER.AUTH.account_security_unavailable` 且不进入业务 handler；closed/suspended/stale/not-found 均不泄露资料。
- Durable terminal event 必须幂等收回已有 realtime connection、presence、lease、ticket、CallSession 和 media room access；重复、乱序、重试和跨节点消费不得恢复或遗留访问权。
- outbox/consumer retry receipt、terminal DLQ、日志、trace 与指标 label 不能携带 accountId、personaId 或原始 payload；terminal DLQ 只能保存不可逆摘要和 source PEL 引用，必须在受控恢复前保留原始 source PEL 未 ACK，且其恢复 marker 不得被普通 retry TTL 过期删除，禁止用已脱敏 DLQ 重建事件。媒体 metadata、CAS original 与 public slice 的 residual probe 必须共同为零才可宣布完成。
- 媒体清理必须先持久化 artifact work，再删除 metadata；公开 slice 与资产专属派生前缀必须物理撤销，私有 CAS/processed object 仅在剩余 MediaAsset 引用为零时删除。共享 CAS 删除必须与新 MediaAsset 引用经持久化 deletion fence 串行化：deleting 期间拒绝新引用，删除完成后才允许重建引用。任一对象存储删除失败必须保留 work 并阻止 inbox completion，重试不得误删仍被其他资产引用的 CAS。

## 4. 契约引用

- lifecycle/outbox canonical：`quwoquan_service/services/user-service/contracts/account/user_account`
- session/credential canonical：`quwoquan_service/services/user-service/contracts/account/account_session`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 owner 注销原子成功且重放返回稳定终态

- GIVEN 当前用户是 authenticated account owner，账号尚未关闭。
- WHEN 用户确认注销，或以同一幂等键重放 CloseAccount。
- THEN 首次提交原子撤销全部会话、擦除凭证和隐私字段、退役 Persona，并持久化 UserAccountClosed outbox。
- THEN 首次结果为 closed 且 idempotentReplay=false；重放返回同一 closedAt 且 idempotentReplay=true。

<a id="gwt-002"></a>
### GWT-002 越权或事务失败不产生部分注销

- GIVEN 请求者不是 owner，或事务中的任一步骤失败。
- WHEN 调用 CloseAccount。
- THEN 返回 metadata 定义的结构化失败；账号、会话和凭证保持原状，且不发布关闭事件。
- THEN App 保留当前登录态并提供可重试入口。

<a id="gwt-003"></a>
### GWT-003 跨域最终清理并回到游客安全态

- GIVEN authenticated owner 从 canonical `settings.account_security` 进入 production Remote 注销旅程，账号仍处于 active 终态。
- WHEN 用户取消确认、确认后收到 canonical failure，或确认成功并使 CloseAccount 提交 `UserAccountClosed` durable fact。
- THEN 取消确认不发出注销命令；canonical failure 保留当前会话、账号安全页与可重试入口，不启动本地终态清理也不展示成功。
- THEN typed `closed` 结果到达后，Content、Chat、Circle、Notification 与 Search 消费 durable fact，Content-owned recommendation cleanup 完成 residual probe，App 执行本地注销流程。
- THEN 每个消费者幂等清理或匿名化所属数据，Recommendation residual probe 为零，失败进入重试/DLQ；旧 token 不能继续访问。
- THEN App 仅在云侧成功后写入加密清理回执，清理本地凭证、待投递队列、当前 actor 草稿、账号关联缓存与 push/来电秘密状态，并进入不会再次触发登录门的安全首页。
- THEN 清理全部读回为零后删除回执；进程崩溃或其他设备注销触发 `account_deleted` 时由启动绑定恢复同一幂等清理，失败保留回执继续重试且不能恢复已关闭会话。

<a id="gwt-004"></a>
### GWT-004 已签发旧凭据立即被所有入口拒绝并回收长连接

- GIVEN 一个 active account 的 access JWT、WS ticket 和 RTC room access 已签发，且至少一个 WS 或 CallSession 已建立。
- WHEN CloseAccount 的同一 PostgreSQL transaction 写入 closed/authEpoch/session revoke/outbox，或 Suspend 写入 suspended/authEpoch/outbox。
- THEN 任一资源 HTTP 入口、WS consume/upgrade、RTC join/renewal 在动作执行前得到同一 authority 终态，旧 epoch 不可访问，authority 不可用也不可访问。
- THEN durable event 最终清除既有连接和 media access；所有 consumer 失败可重试、超过阈值以无 PII DLQ 记录可恢复引用且原始 source PEL 保持未 ACK，受控恢复只能释放该 PEL 重新消费，残留 probe 为零。

## 6. 依赖

- 前置要求：[`settings-and-device-token`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 跨域最终清理并回到游客安全态

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：实现、local_contract、API integration 与直接 `spec_ref` 已齐。Gamma 真机执行仍依赖可用设备、gamma-local Provider substitute 与同候选观测回执；Prod 执行另需经批准注入的真实 Provider 和 managed observability 凭据。禁止用 Mock 或跳过门禁代替。
- 目标：环境材料与设备到位后通过 `stackctl` 启动 full workload，执行一次性 install identity 的账号注销 Patrol、旧 refresh/access 拒绝、下游 residual probe、DLQ 恢复与排空演练并保留制品。
- 完成判定：`GWT-003` 的 production journey 绑定同一 commit、ContractGraph、candidate、环境与真实 Provider，且 Android 物理设备和 iPhone 物理设备 `ReadinessResultBundle` 均为 passed；旧 refresh/access 拒绝、下游 residual probe、DLQ 恢复与排空证据同属该 candidate。failed、blocked、skipped、模拟器或测试 double 均不计通过。
