# chat-service

## Purpose

云侧聊天服务：会话、消息投递、联系人。

---

## ADDED Requirements

### Requirement: 会话管理

系统 MUST 提供会话创建、列表、详情接口。

#### Scenario: 会话列表

- **WHEN** 客户端请求 `GET /v1/chat/conversations`
- **THEN** 系统返回该用户的会话列表，含最后消息、未读数等

#### Scenario: 会话详情

- **WHEN** 客户端请求 `GET /v1/chat/conversations/{conversationId}`
- **THEN** 系统返回会话元数据与成员

### Requirement: 消息投递

系统 MUST 提供消息发送、拉取、已读状态接口。

#### Scenario: 发送消息

- **WHEN** 客户端请求 `POST /v1/chat/conversations/{conversationId}/messages` 携带 content、type
- **THEN** 系统落库并投递，返回 messageId

#### Scenario: 消息分页拉取

- **WHEN** 客户端请求 `GET /v1/chat/conversations/{conversationId}/messages?before=&limit=20`
- **THEN** 系统返回消息列表，支持游标分页

### Requirement: 联系人

系统 MUST 提供联系人列表与搜索接口。

#### Scenario: 联系人列表

- **WHEN** 客户端请求 `GET /v1/chat/contacts`
- **THEN** 系统返回联系人列表

#### Scenario: 联系人搜索

- **WHEN** 客户端请求 `GET /v1/chat/contacts/search?q=`
- **THEN** 系统返回匹配的联系人

### Requirement: 群聊创建与成员管理（最小可用）

系统 MUST 支持创建群聊会话，并提供成员增删能力，满足端侧“创建新群聊、从圈子/群聊选择成员”的交互。

#### Scenario: 创建会话（直聊/群聊）

- **WHEN** 客户端请求 `POST /v1/chat/conversations` 携带 type=direct|group、memberIds、title（可选）
- **THEN** 系统创建会话并返回 conversationId

#### Scenario: 添加成员

- **WHEN** 客户端请求 `POST /v1/chat/conversations/{conversationId}/members` 携带 memberIds
- **THEN** 系统添加成员并返回 204（需权限校验）

#### Scenario: 移除成员

- **WHEN** 客户端请求 `DELETE /v1/chat/conversations/{conversationId}/members/{memberId}`
- **THEN** 系统移除成员并返回 204（需权限校验）

#### Scenario: 会话设置（静音/置顶/已读，预留）

- **WHEN** 客户端请求 `PATCH /v1/chat/conversations/{conversationId}/settings` 携带 muted、pinned 等字段
- **THEN** 系统更新设置并返回最新 settings
