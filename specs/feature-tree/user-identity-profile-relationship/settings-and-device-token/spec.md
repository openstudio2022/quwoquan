# L2 业务能力：设置、设备与账号安全

## 目标

为已登录账号提供可真实读写的通知、隐私、通话、外观设置，管理设备推送端点与登录凭证，
并提供 App 内可达的自助账号注销。设置页不是静态入口集合；每个动作都必须绑定对象级
typed Facet、结构化错误、幂等/并发合同和可审计的云侧状态。

## 范围

- `UserSettings`：通知、隐私、通话、外观四个 named Slice 与对应命令。
- `DeviceRegistration`：账号拥有的设备及 APNs VoIP / FCM endpoint，token 加密落库。
- `CredentialBinding`：凭证列表、手机号/运营商绑定与最后凭证保护。
- `UserAccount` 生命周期：用户二次确认后立即进入不可逆 `closed` 终态，吊销全部会话与
  凭证、退役 Persona、擦除用户域 PII/SECRET，并以 durable `UserAccountClosed` 事件
  驱动内容、聊天、圈子、通知、搜索与推荐域删除或匿名化。
- 运营账号处置：受信 Product Ops 决策可将 `active` 账号切换为可逆 `suspended`，
  原子撤销会话、递增 auth epoch 并发布最小化 enforcement 事实；经申诉或治理复核批准后，
  只能通过显式 Restore 决策恢复 `active`。

## Out of Scope

- 数据导出与撤回同意；它们属于后续独立数据主体权利 Story，不得伪装为已完成入口。
- 已注销账号恢复。当前产品明确选择“立即不可逆注销”，因此不设计冷静期与撤销双轨；
  用户可在注销完成后以已释放的凭证重新注册新账号，但历史身份不得恢复或重绑。
- 在 App、前端页面或任意下游直接编辑账号状态、绕过受信运营决策恢复账号，或以
  `UserAccountClosed` 清理器实现封禁。
- 第三方登录正式凭据与真机发布证据，继续由 R-AUTH-001 管理。

## 核心合同

1. 字段、错误码、operation、route、surface 和事件以 metadata 为唯一真相源。
2. 客户端不提交聚合版本；服务端在对象内部执行版本 CAS 与有限重试。
3. 注销提交的账号终态、session/credential 失效、Persona 退役、用户域隐私清理和
   outbox 必须同一事务完成；任何一步失败都不得留下部分终态。
4. `UserAccountClosed` 至少一次投递；消费者以 `eventId + digest` 幂等，成功落业务状态
   后才 ACK，有限重试后进入带 TTL 的 DLQ。
5. 事件只携带 `userId/personaIds/accountState/updatedAt`；不得传播手机号、token、
   昵称或其他 PII。
6. 注销成功后 App 清理本地会话并进入不会重新触发登录门的安全首页。
7. `closed` 只允许保持 closed；只允许 `active → suspended → active`，且第二次转换的
   唯一入口是具备 OIDC/服务凭证与审批审计链的 enforcement decision。
8. Suspend 与 Restore 必须原子持久化 accountState、authEpoch、receipt/outbox；Suspend
   同事务撤销 refresh sessions。认证、refresh 和服务鉴权一律拒绝 suspended 或旧 epoch
   token；state reader 不可用时 fail-closed。
9. 下游按各自数据边界消费 `UserSuspended/UserRestored`，以可逆 restriction projection
   隐藏/恢复公开可见性、写入与通知；禁止删除数据或调用不可逆 account closure 路径。

## SLO 与观测

- 设置读写与账号安全命令：p95 ≤ 1.5s，可用性 ≥ 99.9%。
- 注销事务：p95 ≤ 3s；outbox 发布目标 1 分钟内，下游清理运营目标 15 分钟内，
  用户承诺上限 30 天（依法保留记录除外）。
- 账号封禁命令：p95 ≤ 1.5s，旧 token 拒绝生效目标 ≤ 30s；下游 restriction projection
  在 5 分钟内收敛，pending、重试、DLQ、epoch mismatch 与恢复延迟均必须告警。
- 指标必须覆盖设置写失败、设备端点失败、注销 outbox 失败、各下游消费重试/DLQ；
  label 禁止包含账号、Persona 或凭证值。

## 验收标准

- A1：四类设置可读写、失败回滚且重进页面读取云侧投影。
- A2：设备 endpoint 与凭证命令具备加密、唯一性、幂等与最后凭证保护。
- A3：账号注销可达、二次确认、事务终态、重复请求幂等，旧 session 立即失效。
- A4：注销释放凭证唯一键并擦除 PII/SECRET；同凭证可创建全新账号但历史数据不恢复。
- A5：所有声明的下游消费者具备 durable、幂等、重试、DLQ、观测和测试证据。
- A6：local_contract、api_integration、user_acceptance 证据与 readiness/CR 路径一致。
- A7：受信 Suspend/Restore 决策、申诉审批、closed 不可恢复、会话撤销、auth epoch、
  可逆跨域投影和 App 结构化受限体验都具备三层测试与四环境证据。
