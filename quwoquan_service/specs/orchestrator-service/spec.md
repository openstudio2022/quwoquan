# orchestrator-service

## Purpose

云侧编排服务：承载跨服务流程编排与聚合响应。业务服务之间不直接调用；需要多服务数据的请求由 Orchestrator 调用 Content/Circle/User/Ops/Assistant/Chat 聚合完成。

---

## ADDED Requirements

### Requirement: 发现流编排（Feed 聚合）

系统 MUST 提供发现流编排接口，聚合用户画像、行为与内容结果，返回端侧直接可渲染的 Feed。

#### Scenario: 聚合发现流

- **WHEN** 客户端请求 `GET /v1/orch/discovery/feed?type=&page=1&limit=20`
- **THEN** 系统调用 User 获取 profileSnapshot，调用 Ops 获取 visits/行为摘要（可选），调用 Content 获取候选内容与推荐排序，并返回聚合后的 feedItems

### Requirement: 圈子流编排（活动流聚合）

系统 MUST 提供圈子活动流编排接口，聚合圈子信息、用户在圈子内的权限与推荐结果。

#### Scenario: 聚合圈子活动流

- **WHEN** 客户端请求 `GET /v1/orch/circles/{circleId}/activities?page=1&limit=20`
- **THEN** 系统调用 Circle 获取 activities 与成员/权限概要，调用 Ops 获取圈内行为摘要（可选），按推荐策略返回聚合结果

### Requirement: 创建群聊编排（可选）

系统 MAY 提供创建群聊编排接口，用于“从圈子/群聊选择成员 → 创建会话”的跨域流程聚合。

#### Scenario: 从圈子选择成员创建群聊

- **WHEN** 客户端请求 `POST /v1/orch/chat/group-conversations` 携带 circleId、memberIds、title（可选）
- **THEN** 系统校验用户在圈子内权限（Circle），补全成员信息（User/Chat contacts），调用 Chat 创建会话并返回 conversationId

### Requirement: 错误处理与超时

系统 MUST 为下游调用设置超时与降级策略，避免单服务故障拖垮端侧请求。

#### Scenario: 下游超时降级

- **WHEN** 某下游服务超时或不可用
- **THEN** 系统返回可降级的响应（如缺少部分字段的 feedItems）或明确错误码，并将失败写入 Ops 日志

