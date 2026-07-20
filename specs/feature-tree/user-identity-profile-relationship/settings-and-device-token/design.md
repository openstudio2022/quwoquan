# 设置、设备与账号安全设计

## 对象边界

| 对象 | 职责 | 一致性边界 |
|---|---|---|
| `UserSettings` | 通知、隐私、通话、外观四个 named Slice | 单聚合 version CAS；同值命令返回幂等回执 |
| `DeviceRegistration` | 账号拥有的设备及 push endpoint | 父聚合与 owned endpoint 同事务；token 仅存 AES-GCM 密文与 keyed fingerprint |
| `CredentialBinding` | 登录凭证绑定、解绑与脱敏列表 | 数据库唯一约束串行化；禁止应用层“先查再写” |
| `UserAccount` | 账号 active/closed 生命周期 | 注销安全终态事务 + durable outbox |

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
  并观测 outbox/consumer/DLQ 指标。
- Prod：正式凭据、真机和受保护发布审批齐备后才能登记 readiness 环境证据。

Schema 与安全终态为前向变更，不通过恢复已注销账号回滚。代码回滚只能发生在尚未执行
注销的账号；已提交事件必须由兼容当前 canonical 事件的消费者继续排空。
