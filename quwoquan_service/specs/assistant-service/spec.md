# assistant-service

## Purpose

云侧助手服务：Run/ReAct 网关、工具、模板、域配置、反馈同步与学习数据消费。

---

## ADDED Requirements

### Requirement: Run 与 Stream 接口

系统 MUST 提供 Run 与 Stream 接口，与端侧 personal-assistant 契约对齐。

#### Scenario: Run 同步

- **WHEN** 客户端请求 `POST /v1/assistant/runs` 携带 messages、contextScopeHint、userProfileSnapshot 等
- **THEN** 系统执行 ReAct 主循环并返回完整 AssistantRunResponse

#### Scenario: Run 流式

- **WHEN** 客户端请求 `POST /v1/assistant/runs/stream`
- **THEN** 系统以流式返回 trace 与最终 response

### Requirement: 反馈与学习数据上报

系统 MUST 提供 interactionEvents 与 scorecards 上报接口，供端侧 Sync 推送。

#### Scenario: 交互事件上报

- **WHEN** 客户端请求 `POST /v1/assistant/learning/events` 携带 interactionEvents 数组
- **THEN** 系统落库并返回 204

#### Scenario: 评分卡上报

- **WHEN** 客户端请求 `POST /v1/assistant/learning/scorecards` 携带 scorecards 数组
- **THEN** 系统落库并返回 204

### Requirement: historicalRetrievalFeedback 供给

系统 MUST 在 Run 时消费历史反馈，将 historicalRetrievalFeedback 注入上下文。

#### Scenario: 反馈注入 Run

- **WHEN** Run 请求的 contextScopeHint 含 historicalRetrievalFeedback
- **THEN** 系统将反馈纳入模板与推理上下文

#### Scenario: 反馈可由云端补充

- **WHEN** 端侧未传 historicalRetrievalFeedback 但 userId/sessionId 可查
- **THEN** 系统可从不完整上报中补充最近反馈供 Run 使用

#### Scenario: 反馈与学习闭环

- **WHEN** 端侧经 Sync 上报 interactionEvents、scorecards 至本服务
- **THEN** 系统落库后，下次 Run 可将 historicalRetrievalFeedback（含 feedbackStats、reasonCodeDistribution、domainDistribution 等）注入 contextScopeHint，实现反馈→学习闭环

### Requirement: 策略与模板拉取

系统 MUST 提供策略与模板拉取接口，支持 pullPolicy。

#### Scenario: Policy 拉取

- **WHEN** 客户端请求 `GET /v1/assistant/policy?versionHint=`
- **THEN** 系统返回 policy 快照，含模板版本、实验分桶等
