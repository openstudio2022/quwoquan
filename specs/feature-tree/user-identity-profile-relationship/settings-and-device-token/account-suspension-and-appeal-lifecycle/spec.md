# L3 Story：账号封禁、恢复与申诉生命周期

## 用户价值

当账号因可信治理决策被限制时，用户得到不泄露审核证据的结构化受限说明和申诉续接；限制
即时阻止旧凭证继续使用，并跨内容、聊天、圈子、通知、搜索和推荐一致生效。申诉获批后，
用户以新会话安全恢复，不会误恢复已注销身份或旧 token。

## In Scope

- `UserAccount` 的 `active → suspended → active` 唯一可逆状态机，及 `closed` 不可恢复
  约束。
- 由 `moderation_case_v1` 和 `appeal_case_v1` 受信审批链产出的 internal
  `SuspendAccount` / `RestoreAccount` decision。
- 原子 account state、auth epoch、session/refresh revoke receipt、outbox 与审计写入。
- `UserSuspended/UserRestored` 最小化事件，以及 Content、Chat、Circle、Notification、
  Search、Recommendation 的幂等可逆 restriction projection。
- App 结构化 `account_suspended` 错误面、申诉/支持续接与安全落点；恢复后仅允许重新登录后
  继续原目标。

## Out of Scope

- App、客服页面或下游服务直接变更 `accountState`，或客户端提交审核理由/证据。
- 恢复 `closed` 账号、恢复注销后个人数据/凭证，或通过恢复决定规避注销清理。
- 利用 `UserAccountClosed` 消费者匿名化或删除 suspended 账号的数据。
- 自动化处罚模型、处罚策略阈值、人工审核证据采集产品细节；本 Story 只消费已批准的受信决策。

## 业务规则

1. UserAccount 是 `accountState` 与 `authEpoch` 的唯一 owner。只允许受信 internal decision
   在行锁事务中改变状态。
2. `closed` 是终态；Suspend 不能作用于 closed，Restore 永远不能恢复 closed。只有
   `active → suspended` 与 `suspended → active` 合法。
3. Suspend 与 authEpoch 递增、全部 AccountSession/refresh binding 撤销、command receipt、
   `UserSuspended` outbox 同一事务提交。Restore 不恢复旧 session/token，必须递增 epoch 并
   发布 `UserRestored`。
4. decision 必须有唯一 decision id/digest、不可伪造的 OIDC/服务主体、opaque case ref、
   request/trace id 和符合 `workflow.yaml` 的审批状态；相同 decision 可幂等重放，冲突
   digest fail-closed。
5. 认证登录、refresh、服务认证和长连接续期必须验证 account state 与 authEpoch。reader
   不可用、状态未知、epoch 不匹配或 suspended 一律拒绝，不能降级到旧 session。
6. 下游只落可逆 restriction projection：隐藏可见性、拒绝写入或抑制投递；保留 canonical
   数据与 event inbox。Restore 只恢复允许的后续行为，不补发过期通知、不恢复旧 token。
7. 用户面只展示 metadata 定义的结构化错误和可执行的申诉/支持入口，不显示违规理由、证据、
   case id、内部审计或原始异常。

## 验收意图

- `contract`：metadata、typed internal decision、错误、event payload 与 audit fields 单轨一致。
- `GWT`：状态转移、幂等/冲突、closed 拒绝恢复、session revoke、epoch 拒绝、投影重放与
  fail-closed 均可复验。
- `SIT`：真实 PostgreSQL/Redis/Mongo/ES 上 Suspend→旧 token 拒绝→跨域受限→Restore→
  新会话恢复，覆盖 retry、DLQ、并发 decision 与延迟 SLO。
- `UAT`：真实 Gamma 设备登录受限说明、安全落点、申诉状态与批准后目标续接；不以 widget
  fake 或只读页面替代。

## 商业与运维

- Suspend/Restore p95 ≤ 1.5s；旧 token 拒绝目标 ≤ 30s；下游 restriction 收敛 ≤ 5min。
- 每个 consumer group 记录 lag、pending claim、重试、DLQ、digest conflict、projection age；
  账号、Persona、case ref 不得成为 metric label 或明文日志字段。
- 发布前必须在 Alpha/Beta/Gamma/Prod 分层取得证据。Prod 仅可由具备审批、密钥、回滚版本和
  SLO guardrail 的 `stackctl deploy --target prod-hosted` 触发；没有这些输入时保持
  `GATE_BLOCK`。
