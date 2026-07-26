# L3 Story：主动订阅投递 (`proactive-subscription-delivery`)

> 所属能力：[`runtime-assistant`](../spec.md)
>
> Journey / Scenario：[`JNY-009 / SCN-020`](../../../spec.md#scn-020)
>
> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望主动技能订阅（每日助手、新闻简报、股票哨兵、出行管家）按 cron lease 触发，产出投递到用户收件箱（AppMessage）或授权会话，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- SkillSubscription tick lease、失败补偿与投递审计状态
- UserSettings 助手总开关/UTC 静默时间、敏感技能 consent、日频控与 cooldown
- AppMessage 收件箱投递与会话成员/技能身份门控

### Out of Scope

- 通知通道实现（归 notification 域）

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 订阅触发与投递

- 只有 `active` 订阅可进入投递；`paused` / `archived` 立即清除待补偿坐标且不得投递。
- 首次调度与失败补偿必须复用同一 `deliveryId`，Conversation、Run、AppMessage/Chat `clientMsgId` 由该坐标派生，超时重试不得制造重复副作用。
- production composition 必须启动内置 scheduler：进程启动立即 tick，随后至少每分钟 tick；不得依赖仓库外未声明的定时器。多实例并发仍由订阅级 Redis lease 收敛。
- 每个订阅必须持久化并按索引查询 `nextAttemptAt`；调度器短暂停机后仍按原计划时间生成 `deliveryId` 补发，禁止因错过精确分钟永久漏发。
- 投递成功、失败与业务抑制必须收敛 `deliveryState`；失败按 5 分钟起步、最大 1 小时指数退避补偿，成功或业务抑制推进到下一 cron。
- 每次 tick 必须记录 `assistant_subscription_cron_tick_total{outcome}`；30 分钟无成功 tick 触发停摆告警。

<a id="req-002"></a>
### REQ-002 商用投递门控

- 投递前必须以订阅权威 `owner.userId` 从 user-service 回查同一账号的 `assistantEnabled` 与 UTC `quietHoursStart/End`；依赖缺失、鉴权失败、owner 不一致或畸形响应一律 fail-closed。
- 敏感 Skill 必须仍有有效 consent；用户或会话投递都必须执行 `maxPerDay` 与 `cooldownMinutes`。
- user 目的地必须等于订阅 `owner.userId`。
- conversation/group 在创建时与每次投递前都必须经 chat 公开成员 Reader 同时确认创建者 Persona 仍是成员，且存在与订阅 `skillId` 一致的 assistant 成员。
- 任一成员已移除或身份变化时禁止创建或清除待补偿坐标，不创建 Run、不回帖。
- `quietHoursPolicy` 当前单轨只允许 `inherit_user_setting`；默认 `maxPerDay=1`、`cooldownMinutes=60`。

<a id="req-003"></a>
### REQ-003 Redis 幂等与频控

- 每个 `deliveryId` 必须经 300 秒 Redis `SetNX` lease，多实例不得重复进入副作用。
- UTC 自然日频控必须通过 48 小时 Redis delivery slot 原子占位；同一 `deliveryId` 的失败补偿复用原 slot，其他 delivery 不得越过 `maxPerDay`。
- Redis 未配置或读写失败必须返回结构化失败，禁止降级为无租约/无频控投递。

## 4. 契约引用

- canonical：`quwoquan_service/services/assistant-service/contracts/assistant/skill_subscription/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 订阅触发与投递

- GIVEN 用户创建了 active 的主动技能订阅。
- WHEN production 内置 scheduler 启动即执行并按分钟 tick 领取到期订阅，或授权内部 tick 操作触发同一应用服务。
- THEN 服务端复核 active 状态、敏感技能 consent、UserSettings 总开关/静默时间、cooldown、日配额及会话 assistant 成员/技能身份。
- THEN 门控通过时只创建一次 Run 与 AppMessage/Chat 消息，并持久化 `lastDeliveredAt`、清空 pending/failure。
- THEN 重复 tick 被 lease 抑制；外部投递失败保留同一 `deliveryId`、错误码与失败次数，退避后按稳定幂等坐标补偿。
- THEN tick 晚于 `nextAttemptAt` 到达时仍以原计划时间补发，并在成功后推进下次调度。
- THEN paused/archived、撤权、助手关闭、静默、超频或目标成员失效时在外部副作用前抑制，并输出有界原因指标。

## 6. 依赖

- 前置要求：[`runtime-assistant`](../spec.md) 的范围、要求与 SIT。
- 上游 Reader：user-service `ResolveAssistantDeliveryPolicy`、chat-service 会话成员 Reader。
- 下游命令：notification-service AppMessage command 或 chat-service SendMessage。
- 运行依赖：assistant-service 内置 scheduler、MongoDB 权威订阅状态、Redis lease/delivery slot。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

- 无。
