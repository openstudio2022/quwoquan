# L3 特性：proactive-subscription-delivery

## 功能说明
- 主动技能订阅（每日助手、新闻简报、股票哨兵、出行管家）按 cron lease 触发，产出投递到用户收件箱（AppMessage）或授权会话。

## 约束
- tick 领取必须经 Redis lease（`SetNX` + TTL），多实例不重复投递。
- 会话/群投递采用 inviter opt-in：投递前校验小趣仍是会话成员、订阅 active、频控/静默/去重通过。
- 用户收件箱走 AppMessage（notification 域），会话投递复用 chat SendMessage，不新增第二消息通道。

## 验收标准
- A1：订阅创建→tick 触发→投递→用户回流链路可用。
- A2：暂停/取消订阅后不再投递；频控与静默生效。
- A7：订阅状态机与投递契约测试可复跑。
