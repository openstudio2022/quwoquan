# run-stream-policy 设计

## 设计动因

Run 同步/流式协议与策略模板此前只覆盖「启动→流→终态」半程：无取消命令、无会话/轮次查询面、终态重放依赖端侧本地存储。本 L2 把 Run 协议补成完整状态机，并保持单主线（StartAssistantRun 是唯一执行入口，SSE 只是 transport）。

## Run 状态机

```
running ──complete──> completed
   │──fail──────────> failed
   └──cancel────────> cancelled
```

- 三个终态互斥；`CompleteTurn` 为 CAS，已终态重复提交幂等返回存量（取消竞态下后到的 completed 被丢弃）。
- `CancelAssistantRun`（POST /assistant/runs/{runId}/cancel）：owner 校验后 CAS `running→cancelled` 并中断进程内执行（cancel registry）；已终态幂等返回当前信封。
- SSE 事件补 `assistant.turn.cancelled` 终态事件；重放已终态 turn 时按 status 选择 final/failed/cancelled 事件。

## 查询面（会话生命周期数据源）

- `ListAssistantConversations`：GET /assistant/conversations，owner 维度 keyset 分页（updatedAt desc + conversationId tiebreak，cursor 不透明字符串）。
- `ListConversationTurns`：GET /assistant/conversations/{conversationId}/turns，返回终态轮次摘要（`AssistantTurnSummaryView`：turnId/status/inputText/answerText/skillId/createdAt/completedAt），createdAt desc keyset 分页；过程时间线按需走 `GetAssistantRun`。
- 端侧历史列表、transcript 恢复、技能中心「最近会话」都消费这两个查询，不维护本地第二真相源。

## 流式协议

- 信封：`assistant_stream_event`（seq 单调、eventType、payload、runtimeFailure），断线按 resumeToken/seq 重放。
- 阶段事件：turn.started → skill.selected → reasoning/trace → answer.delta* → answer.final → turn.completed|failed|cancelled。
- 策略模板路由（policy-template-routing）：按 skill/domain 选择 prompt/预算模板，模板版本随 run 持久化，可灰度回滚。

## 非功能

- StartAssistantRun p95 1.5s / 可用性 99.9%；SSE timeout 190s；List 查询 p95 500ms。
- Cancel 命令 p95 300ms；取消后 2s 内流终止。
