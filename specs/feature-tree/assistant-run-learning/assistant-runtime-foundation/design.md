# 设计说明：assistant-runtime-foundation

## 设计动因

助手域四个聚合（AssistantConversation、AssistantRun/Turn、SkillSubscription、SkillConsent）此前以进程内 map 或缺失 receipts/outbox 的形态运行，重启丢状态、多实例重复投递、consent 存在失败开放分支。本 L2 将其收敛为业务对象标准 packet，与 `runtime/system-architecture-and-engineering-guide` 的对象范式（design.md「按真实写入场景裁剪并发与幂等」）对齐。

## 对象与写入形态

| 对象 | kind | 写入形态 | 存储 |
|---|---|---|---|
| AssistantConversation | aggregate_root | 一次创建（conversationId 唯一约束）+ 轮次推进内部 CAS | MongoDB `assistant_conversations` |
| AssistantRun/Turn | aggregate_root | 一次创建（runId）+ 状态机 pending→streaming→completed/failed 内部 CAS | MongoDB `assistant_runs`（含 StreamState/ResumeToken） |
| SkillSubscription | aggregate_root | 一次创建 + 状态命名迁移；tick 经 lease 领取 | MongoDB `skill_subscriptions` + receipts + outbox |
| SkillConsent | aggregate_root | grant/revoke 命名迁移（版本化事实 + 事件） | PostgreSQL `skill_consents` |

- Store 为对象专属 `Load + Commit`，Commit 原子提交 state/version、幂等 receipt 与同库 outbox；查询走 named Reader。
- cron/intersection 领取：Redis `SetNX` lease（key 含 tick 窗口，带 TTL），替代内存 claim；语义对齐 metadata `acquireDueLeases`。
- SSE：turn 的 StreamState/ResumeToken 随聚合持久化；重启后 resume 请求返回明确的可恢复/已失效语义，不再 404。
- consent gate：agent loop 工具执行点对 `RequiresConsent` 技能强制查询 active consent，store 不可用或查询失败一律拒绝（fail-closed）；`creationAssistantEnabled` 不再以"双 store 缺失"放行。

## 端侧装配

- 对象级 Facet：ConversationRun / SkillSubscription / SkillConsent / Learning / Personalization / PersonalData / XiaoquSearch / CreationSuggest，各 ≤10 方法；production Remote-only，alpha 由 `quwoquan_cloud_mock` 注入。
- 错误单轨：全部经 runtime mapper 产出 `CloudException`/`RuntimeFailure`；删除吞异常 fallback 与假兜底数据。

## 未来演进

- run 向量索引（metadata 已声明 1536 维）待检索场景启用；当前只建常规索引。
- 多实例 SSE 粘性与断线续传的跨实例恢复，依赖 realtime 域（B10）能力，本 L2 先保证单实例正确与重启语义。
