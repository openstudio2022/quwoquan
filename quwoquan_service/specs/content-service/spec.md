# content-service

## Purpose

云侧内容服务：发现流、Feed、发布、媒体、帮读摘要、内容推荐与内容行为反馈。

---

## ADDED Requirements

### Requirement: 发现流 Feed 接口

系统 MUST 提供发现流 Feed 接口，支持按类型（微趣/美图/视频/文章）分页拉取，支持个性化排序。

#### Scenario: 按类型拉取 Feed

- **WHEN** 客户端请求 `GET /v1/content/feed?type=photo&page=1&limit=20`
- **THEN** 系统返回该类型内容列表，含 id、标题、封面、作者、发布时间、互动数等字段

#### Scenario: 支持推荐排序

- **WHEN** 请求含 `sort=recommend` 且用户已登录
- **THEN** 系统按用户画像与行为进行个性化排序返回

### Requirement: 内容推荐能力

系统 MUST 提供内容推荐能力，输入用户画像与行为，输出推荐内容 ID 列表。

#### Scenario: 推荐接口可用

- **WHEN** 客户端请求 `POST /v1/content/recommend` 并携带 userId、候选池、数量
- **THEN** 系统返回推荐内容 ID 列表，按相关性排序

#### Scenario: 推荐输入可含行为信号

- **WHEN** 请求含记录点击、曝光、停留等行为
- **THEN** 系统将行为纳入推荐计算

#### Scenario: 推荐输入可含用户画像与 Visit

- **WHEN** 请求含 userId
- **THEN** 系统可从 User 服务拉取画像快照、从 Ops 服务拉取 Visit 与行为数据，作为推荐输入

### Requirement: 内容行为上报

系统 MUST 提供内容行为上报接口，支持显式与隐式反馈，eventType 至少包含：impression（曝光）、click（点击）、dwell（停留，含 durationMs）、like（点赞）、favorite（收藏）、dislike（不感兴趣）、report（举报）、share（分享）。

#### Scenario: 行为上报成功

- **WHEN** 客户端请求 `POST /v1/content/behaviors` 携带 contentId、eventType、timestamp、durationMs 等
- **THEN** 系统落库并返回 204

#### Scenario: 支持批量上报

- **WHEN** 请求 body 为行为数组
- **THEN** 系统批量落库，支持幂等与去重

#### Scenario: 反馈驱动推荐优化

- **WHEN** 行为数据落库后
- **THEN** 推荐服务可将曝光未点击、停留时长、点赞/收藏/不感兴趣等纳入特征与策略更新，形成反馈闭环

### Requirement: 帮读摘要接口

系统 MUST 提供帮读摘要接口，支持对微趣/文章生成一句话综述与分维度事实。

#### Scenario: 摘要拉取

- **WHEN** 客户端请求 `GET /v1/content/helper-read/{contentId}`
- **THEN** 系统返回 summary、dimensions、原文链接等

#### Scenario: 帮读卡支持反馈偏好

- **WHEN** 用户对帮读卡执行「反馈偏好」动作（如不感兴趣、偏好调整）
- **THEN** 系统通过内容行为上报接口接收 eventType=feedback_preference 或等价类型，并纳入推荐优化

### Requirement: 媒体与发布

系统 MUST 提供媒体上传与内容发布接口，支持图片、视频、文章等类型。

#### Scenario: 媒体上传

- **WHEN** 客户端请求 `POST /v1/content/media` 携带 multipart 文件
- **THEN** 系统存储并返回 mediaId、url

#### Scenario: 内容发布

- **WHEN** 客户端请求 `POST /v1/content/posts` 携带内容元数据与 mediaIds
- **THEN** 系统创建内容并返回 postId

### Requirement: 评论与回复（最小可用）

系统 MUST 提供评论与回复能力，支持列表拉取、发布、删除，满足端侧 comment_system 组件对接。

#### Scenario: 评论列表拉取

- **WHEN** 客户端请求 `GET /v1/content/posts/{postId}/comments?cursor=&limit=20`
- **THEN** 系统返回按时间倒序的评论列表，支持游标分页

#### Scenario: 发布评论

- **WHEN** 客户端请求 `POST /v1/content/posts/{postId}/comments` 携带 content、replyToCommentId（可选）
- **THEN** 系统创建评论，返回 commentId

#### Scenario: 删除评论

- **WHEN** 客户端请求 `DELETE /v1/content/comments/{commentId}`
- **THEN** 系统校验权限（作者或管理员）后删除并返回 204

### Requirement: 互动状态读取（like/favorite 等）

系统 MUST 提供互动状态读取接口，使端侧可在渲染时判断“我是否已点赞/收藏”等，而不仅仅依赖行为上报。

#### Scenario: 读取用户对内容的互动状态

- **WHEN** 客户端请求 `GET /v1/content/posts/{postId}/reactions?userId=`
- **THEN** 系统返回该用户对该内容的 reaction 状态（liked、favorited、reported 等）

#### Scenario: 读取内容聚合计数

- **WHEN** 客户端请求 `GET /v1/content/posts/{postId}/counters`
- **THEN** 系统返回点赞/评论/收藏/分享等聚合计数，允许准实时（最终一致）更新

### Requirement: 媒体资产状态与异步处理（预留）

系统 MUST 对媒体上传提供状态查询能力，支持异步转码、缩略图生成、内容安全审核等管线化处理。

#### Scenario: 查询媒体状态

- **WHEN** 客户端请求 `GET /v1/content/media/{mediaId}`
- **THEN** 系统返回 status（uploaded/processing/ready/failed）、derivatives（缩略图/转码结果）、moderationStatus 等
