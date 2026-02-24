# user-service

## Purpose

云侧用户服务：认证、Profile、画像快照、分身、profileUpdateProposal 消费与回流。

---

## ADDED Requirements

### Requirement: 认证接口

系统 MUST 提供认证接口，支持登录、登出、token 刷新。

#### Scenario: 登录成功

- **WHEN** 客户端请求 `POST /v1/user/auth/login` 携带凭据
- **THEN** 系统返回 accessToken、refreshToken、userId

#### Scenario: Token 刷新

- **WHEN** 客户端请求 `POST /v1/user/auth/refresh` 携带 refreshToken
- **THEN** 系统返回新的 accessToken

### Requirement: 用户 Profile 与画像快照

系统 MUST 提供 Profile 读取接口，输出用户基础信息与画像快照，供 Assistant 与推荐消费。

#### Scenario: Profile 拉取

- **WHEN** 客户端请求 `GET /v1/user/profile/{userId}`
- **THEN** 系统返回 basicIdentity、ipResidenceProfile、interestTopics、tonePreferences 等

#### Scenario: 画像快照版本化

- **WHEN** Profile 发生变更
- **THEN** 系统更新 profileVersion，支持客户端携带 version 做增量或校验

### Requirement: profileUpdateProposal 消费

系统 MUST 提供 profileUpdateProposal 消费接口，支持创建、确认、拒绝、应用状态流转。

#### Scenario: 提案创建

- **WHEN** Assistant 输出 profileUpdateProposal 并上报
- **THEN** 系统落库并返回 proposalId，状态为 created

#### Scenario: 用户确认

- **WHEN** 客户端请求 `POST /v1/user/profile/proposals/{proposalId}/confirm`
- **THEN** 系统更新状态为 approved，支持用户修改后再 apply

#### Scenario: 提案应用

- **WHEN** 客户端请求 `POST /v1/user/profile/proposals/{proposalId}/apply`
- **THEN** 系统将 updates 写入 Profile，状态为 applied

#### Scenario: 提案拒绝

- **WHEN** 客户端请求 `POST /v1/user/profile/proposals/{proposalId}/reject`
- **THEN** 系统更新状态为 rejected，不修改 Profile

### Requirement: 分身

系统 MUST 支持用户分身能力，允许同一用户在不同场景使用不同身份标识。

#### Scenario: 分身列表

- **WHEN** 客户端请求 `GET /v1/user/avatars`
- **THEN** 系统返回该用户的分身列表

### Requirement: 分身管理（CRUD + 激活）

系统 MUST 提供分身创建、编辑、删除与激活接口，满足端侧 persona 管理与切换场景。

#### Scenario: 分身列表（推荐路径）

- **WHEN** 客户端请求 `GET /v1/user/personas`
- **THEN** 系统返回该用户的 persona 列表（含 isPrimary、isPrivate、displayName、avatarUrl 等）

#### Scenario: 创建分身

- **WHEN** 客户端请求 `POST /v1/user/personas` 携带 displayName、avatarUrl、isPrivate 等
- **THEN** 系统创建 persona 并返回 personaId

#### Scenario: 编辑分身

- **WHEN** 客户端请求 `PATCH /v1/user/personas/{personaId}` 携带可变更字段
- **THEN** 系统更新 persona 并返回更新后的快照

#### Scenario: 删除分身

- **WHEN** 客户端请求 `DELETE /v1/user/personas/{personaId}`
- **THEN** 系统删除（或软删）persona 并返回 204（主 persona 不可删除）

#### Scenario: 激活分身

- **WHEN** 客户端请求 `POST /v1/user/personas/{personaId}/activate`
- **THEN** 系统将该 persona 设为当前激活 persona，并返回 204

### Requirement: 关注关系（follow graph，最小可用）

系统 MUST 提供关注/取消关注与关系查询接口，支撑端侧 isFollowing、followers/following 等字段与列表页面。

#### Scenario: 关注用户

- **WHEN** 客户端请求 `POST /v1/user/follow/{targetUserId}`
- **THEN** 系统创建关注关系并返回 204（需幂等）

#### Scenario: 取消关注

- **WHEN** 客户端请求 `DELETE /v1/user/follow/{targetUserId}`
- **THEN** 系统删除关注关系并返回 204

#### Scenario: 关注/粉丝列表

- **WHEN** 客户端请求 `GET /v1/user/{userId}/following?cursor=&limit=20`
- **THEN** 系统返回关注列表（用户概要）

- **WHEN** 客户端请求 `GET /v1/user/{userId}/followers?cursor=&limit=20`
- **THEN** 系统返回粉丝列表（用户概要）

#### Scenario: 关系查询

- **WHEN** 客户端请求 `GET /v1/user/{userId}/relationship?targetUserId=`
- **THEN** 系统返回 isFollowing/isBlocked 等关系状态

### Requirement: 用户设置（通知/隐私，最小可用）

系统 MUST 提供通知与隐私相关的系统参数设置接口，与端侧 SettingsPage 对接。

#### Scenario: 通知设置读取与更新

- **WHEN** 客户端请求 `GET /v1/user/settings/notifications`
- **THEN** 系统返回通知偏好（如 enablePush、enableMarketing、quietHours 等）

- **WHEN** 客户端请求 `PATCH /v1/user/settings/notifications` 携带更新字段
- **THEN** 系统更新并返回最新设置

#### Scenario: 隐私设置读取与更新

- **WHEN** 客户端请求 `GET /v1/user/settings/privacy`
- **THEN** 系统返回隐私设置（如 allowStrangerMessage、profileVisibility 等）

- **WHEN** 客户端请求 `PATCH /v1/user/settings/privacy` 携带更新字段
- **THEN** 系统更新并返回最新设置

### Requirement: 设备与推送令牌注册（SaaS 对接前置）

系统 MUST 提供设备 push token 注册接口，用于后续对接云厂商推送 SaaS。

#### Scenario: 注册或更新 push token

- **WHEN** 客户端请求 `POST /v1/user/devices/push-tokens` 携带 platform（ios/android）、token、deviceId
- **THEN** 系统保存 token 并返回 204（需幂等与去重）
