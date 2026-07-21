# 设置、设备与账号安全设计

## 对象边界

| 对象 | 职责 | 一致性边界 |
|---|---|---|
| `UserSettings` | 通知、隐私、通话、外观四个 named Slice | 单聚合 version CAS；同值命令返回幂等回执 |
| `DeviceRegistration` | 账号拥有的设备及 push endpoint | 父聚合与 owned endpoint 同事务；token 仅存 AES-GCM 密文与 keyed fingerprint |
| `CredentialBinding` | 登录凭证绑定、解绑与脱敏列表 | 数据库唯一约束串行化；禁止应用层“先查再写” |
| `UserAccount` | 账号 `active/suspended/closed` 生命周期与 auth epoch | 注销安全终态事务；受信封禁/恢复决策 + durable outbox |

页面与 Provider 只依赖上述对象级 Query/Command Facet。production composition 只装配
generated client + Remote adapter；Alpha/test 在独立 runner/mock package 注入同构实现。

## 注销方案裁决

采用“立即不可逆注销”，不引入冷静期、恢复状态或撤销 API。理由：

- UI 已在提交前明确说明不可恢复和删除范围，用户动作语义确定；
- `closed` 单终态比 `closing/cooling_off/cancelled/closed` 更少状态与竞态；
- 凭证在事务中擦除并释放唯一键，用户仍可重新注册全新账号，不需要恢复旧身份；
- 法律或安全审计需要保留的事实只保留不可逆匿名化记录，不保留可登录账号。

若未来产品引入冷静期，必须作为新的状态机变更重新走 spec/acceptance；禁止在当前
`CloseAccount` 上增加隐式恢复分支。

## 运营封禁与申诉方案裁决

封禁不是注销的软别名。`closed` 永远不可逆，`suspended` 仅表示运营处置期间的可逆受限
状态，状态机严格为：

```text
active --[trusted Suspend decision]--> suspended
suspended --[approved Restore decision]--> active
closed --[任何请求]--> closed
```

Product Ops 是 `moderation_case_v1 / appeal_case_v1` 的 owner，负责证据、审批人、case
状态和审计。它在审批完成后，以 OIDC/服务凭证签名的 internal enforcement decision 调用
User Service；UserAccount 仍是 `accountState`、`authEpoch`、session revoke receipt 和
`UserSuspended/UserRestored` outbox 的唯一 owner。申诉批准不允许直写账号或通过 App
绕过 User Service；它只产生 Restore decision。decision payload 只带不透明 case ref、
decision id/digest、action、request/trace id 和最小目标账号引用，不包含审核理由或证据。

## 封禁提交与认证边界

`AccountEnforcementStore.CommitDecision` 是 PostgreSQL 内的事务协调器：

1. 校验 internal principal、decision action、case/appeal 审批状态与不可重放的 receipt。
2. `SELECT ... FOR UPDATE` 锁定 UserAccount；`closed` 只能拒绝，已处于目标状态才返回同一
   receipt 的幂等结果。
3. 首次状态转换递增 `authEpoch`；Suspend 同事务撤销所有 AccountSession/refresh binding，
   且落 `UserSuspended` outbox。Restore 只恢复 account state，不恢复旧 session/token，
   并落 `UserRestored` outbox。
4. 事务提交后，认证、refresh、WebSocket/service authentication 都必须同时验证 account
   state 与 token epoch；enforcement reader 缺失、状态未知或 epoch 不匹配均 fail-closed。

下游复用 `eventId + digest` inbox、pending claim、有限重试和 TTL DLQ，但各自写
`restriction projection` 而非清理数据：

- content/search：隐藏 suspended owner 的 profile、post、comment 与索引，Restore 后按
  projection 回读恢复；
- chat/circle：拒绝发送、成员写与入会动作，保留会话/成员原事实；
- notification：抑制投递并在 Restore 后重新允许后续通知，不补发已过期消息；
- recommendation：过滤 suspended subject 和特征写入，不删除可恢复画像。

任何消费者不得调用 `accountclosure` 的匿名化/删除器，不能用缓存未命中、客户端 header 或
前端分支替代服务端 enforcement reader。

## 注销提交事务

`UserAccountCloseStore.CommitClose` 是 PostgreSQL 内唯一事务协调器，按固定顺序完成：

1. `SELECT ... FOR UPDATE` 锁定 `UserAccount`，已 closed 时进入幂等收敛。
2. 账号写 `closed`，profile version 只在首次提交递增，`closedAt` 保持稳定。
3. 吊销全部 AccountSession；擦除 CredentialBinding 的 secret/key/label 并释放全局唯一键。
4. Persona 退役并擦除公开资料 PII，保留 `personaId` 作为最小跨域归因标识。
5. 删除或匿名化 user 域设置、设备、二维码、联系发现、关系、请求和待处理提案。
6. 写入唯一 `UserAccountClosed` outbox；状态与事件同事务提交。

Facade 不在事务后再次执行安全写。缓存删除是提交后的可恢复副作用：失败记录结构化
异常与指标，但不能把已成功的不可逆终态伪装成回滚。

## 跨域最终一致性

`CloseOutboxRelay` 先将事件写入 `events.user.account` durable Redis Stream，再确认
PostgreSQL outbox。每个消费者使用独立 group：

- content/search/recommendation：删除作品、评论、互动、画像特征与索引；法定留存事实匿名化。
- chat：删除账号私有态，对必须保留的会话/消息审计不可逆匿名化。
- circle：移除成员/管理关系；若 owner 不变量无法安全迁移则重试并进入治理 DLQ，禁止静默孤儿。
- notification：删除通知、投递任务与用户目标引用。
- user 内部 search/tag 投影：删除公开 profile 索引。

消费者执行 `pending claim → read new → validate → inbox/digest → business mutation →
ACK`；失败有限重试，达到阈值后写 DLQ 并设置 TTL。ACK、inbox 完成和业务变更的先后顺序
必须保证进程崩溃后最多重放，不得丢失。

## 并发与幂等

- 两个并发注销由账号行锁串行化；只有一个版本/outbox，另一个返回 `idempotentReplay=true`。
- 旧 token 与注销并发时，服务边界必须同时验证 AccountSession 和账号状态；事务提交后旧
  session 不再可用。
- `eventId` 相同但 digest/version 不同属于协议破坏，消费者 fail-closed，不能覆盖 inbox。
- 下游删除操作按 ID 集合幂等；外部索引删除失败不得提前标记 inbox 完成。

## 四环境与回滚

- Alpha：typed mock/local_contract 验证页面、命令与异常。
- Beta：真实 Remote + seed，验证设置与注销完整用户旅程。
- Gamma：generated client 通过 gateway 验证 AccountSession/UserSettings/CloseAccount，
  并观测 outbox/consumer/DLQ 指标；封禁旅程额外验证旧 token 拒绝、受限主页不可见、申诉
  恢复后的新会话续接和 restriction projection 收敛。
- Prod：正式凭据、真机和受保护发布审批齐备后才能登记 readiness 环境证据。

Schema 与安全终态为前向变更，不通过恢复已注销账号回滚。代码回滚只能发生在尚未执行
注销的账号；已提交事件必须由兼容当前 canonical 事件的消费者继续排空。

封禁的代码回滚也不允许把 `suspended` 静默改回 `active`：已发布 decision/outbox 必须继续
由版本兼容的消费者排空；恢复只能使用审计链完整的 Restore decision。Prod 部署前必须演练
Suspend/Restore 各一次、验证 epoch 拒绝与下游 lag/DLQ 告警。
