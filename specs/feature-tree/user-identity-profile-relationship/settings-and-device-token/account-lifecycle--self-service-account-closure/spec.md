# L3 Story：自助账号注销

## 用户价值

用户无需联系客服即可在 App 内注销账号；提交前明确知道不可恢复、会立即退出以及数据删除
范围，提交后旧凭证和会话不可继续访问，公开身份与关联数据按约定删除或匿名化。

## In Scope

- 设置 → 账号安全 → 注销账号的可达入口、二次确认、结构化失败与成功安全落点。
- `CloseAccount` owner 命令的鉴权、幂等、并发串行化和 `closed` 终态。
- 用户域 session/credential/persona/PII/SECRET 与私有对象的事务清理。
- `UserAccountClosed` durable outbox、跨域消费者、重试、DLQ、指标与告警。
- 已释放手机号或第三方凭证可用于注册全新账号，历史身份和数据不恢复。

## Out of Scope

- 冷静期、撤销注销、旧账号恢复。
- 数据导出与撤回同意。
- 法定留存期限的政策制定；实现仅保证留存事实不可逆匿名化且不能用于重新识别。

## 业务规则

1. 只有当前 authenticated owner 可调用；不得接受客户端传入其他 accountId。
2. 首次成功返回 `accountState=closed`、稳定 `closedAt`、
   `idempotentReplay=false`；重放返回同一终态与 `idempotentReplay=true`。
3. 注销事务任一步失败必须整体回滚；成功时所有 AccountSession 已吊销、CredentialBinding
   已擦除、Persona 已退役、用户域 PII/SECRET 已清理、outbox 已持久化。
4. App 仅在云侧成功后清理本地会话并导航到安全首页；失败时保留当前登录态和可重试入口。
5. 下游消费者允许至少一次重放，不允许丢事件、提前 ACK 或用空成功掩盖清理失败。
6. `recommendation-engine` 是 `content-service` 内的有状态推荐运行时；Python
   `rec-model-service` 只做无账号私有持久状态的评分，不得新增第二个注销消费者或跨服务
   删除共享数据。
7. 有状态推荐清理必须先持久化不可逆 subject tombstone，再删除 Mongo/Redis/进程内状态；
   晚到或重放的行为、搜索、关系、学习与训练事件命中 tombstone 后必须 fail-closed，
   不得在清理后重新物化账号状态。
8. 推荐训练样本与 replay 快照包含账号特征，必须随账号注销删除；受影响的 immutable
   replay dataset 必须进入 `privacy_invalidated` 终态并拒绝训练、评估和发布消费。

## 验收意图

- `contract`：typed command/result、metadata、错误和事件字段严格一致。
- `GWT`：成功、重复提交、并发、事务失败、消费失败与凭证重新注册均有证据。
- `SIT`：User → Content（含 recommendation-engine）/Chat/Circle/Notification/Search
  链路最终收敛，并证明无状态 `rec-model-service` 不持有可清理账号状态。
- `UAT`：用户确认注销后退出到安全态；取消或服务失败不改变账号。

## 商业与运维

- 注销事务 p95 ≤ 3s；outbox 1 分钟内发布；下游清理目标 15 分钟，承诺上限 30 天。
- outbox 失败率、消费者重试/DLQ 和清理延迟必须可观测；日志与 metric label 禁止 PII。
- 推荐清理必须有 Mongo/Redis/内存/training/replay residual probe；任一 probe 非零或
  tombstone 后出现复活写入均为发布阻断。
- Prod 环境证据必须包含真机流程、旧 token 拒绝、下游清理探针和回滚/排空演练。
