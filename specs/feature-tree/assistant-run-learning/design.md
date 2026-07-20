# assistant-run-learning 设计

## 设计动因

小趣私人助理的运行主线（Run/Stream）、策略模板、学习反馈与画像提案此前分散在端侧引擎遗留、服务内 map 状态与散落 prompt 中。本 L1 把它们收敛为一条以业务对象为中心的主线：`AssistantConversation → AssistantRun(Turn) → AgentLoop（技能选择 → ReAct → 工具 → 证据 → 成答）→ 学习事实 → 画像/提案回流`，与 ChatGPT/豆包级对话底线（会话可管理、流式可停止、记忆可见可撤销）对齐，同时保持趣我圈差异化（站内 grounding、交集解释、主动投递）。

## 分层结构

| 层 | 承载 | 真相源 |
|---|---|---|
| 对象契约 | conversation/run/subscription/consent/interaction_event/scorecard 六对象 packet | `contracts/metadata/assistant/**` |
| 服务 | assistant-service（DDD 四层，Mongo/PG/Redis fail-fast 装配） | `services/assistant-service/**` |
| 运行主线 | AgentLoop + ReactRuntime + Tool Registry + SSE 信封 | `internal/application/**` |
| 端侧 | 对象级 Facet（≤10 方法）+ SSE 投影 + transcript 统一时间线 | `quwoquan_app/lib/cloud/services/assistant/**` |
| 学习闭环 | InteractionEvent/Scorecard append fact → 学习画像投影 → 注入/运营摘要 | `learning-event-feedback-injection` |

## 会话生命周期主线（2026-07-20 冻结）

- 会话查询面：`ListAssistantConversations`（owner keyset 分页）与 `ListConversationTurns`（终态轮次摘要分页）是端侧历史列表、会话恢复与续聊的唯一数据源；端侧不再维护本地会话双模型。
- 取消语义：`CancelAssistantRun` 将 running turn CAS 为 `cancelled` 终态并中断执行；已终态取消幂等返回现状。SSE 以 `assistant.turn.cancelled` 终态事件收口。
- run 状态机：`running → completed | failed | cancelled`；终态互斥且不可再迁移，重复完成幂等返回存量。

## 灰度与回滚

- 助手策略（prompt/skill/policy）发布支持按版本灰度与回滚；grounding 与主动投递各有独立 feature flag（见 `commercial_slo_observability.md`）。
- consent fail-closed 不参与灰度：任何环境失败一律拒绝。

## 与子节点关系

- `assistant-runtime-foundation`：对象持久化、consent 门、订阅 lease、端侧 Facet（基座）。
- `run-stream-policy`：Run/Stream 协议、Cancel、策略模板路由。
- `learning-event-feedback-injection`：学习事实、聚合与注入。
- `profile-proposal-apply-loop`：画像提案回流。
- `world-class-trinity-experience-baseline`：统一主线 PRD（Skill 中心化、Markdown-first、偏好回注）。
