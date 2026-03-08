# L2 圈子协作工具 — 设计方案

## 设计动因

解决 spec.md 中 R2.2~R2.3 和 R3 全部约束：圈子缺少协作深度。本 L2 涵盖三个 L3：存储空间、群聊集成、作品发布区。

## 上游输入评审

- spec.md R2.1~R3.4 清晰，acceptance A5/A6 可测。
- 依赖：
  - chat 域：`Conversation.circleId`、`ConversationType.circle`、`Circle.conversationId` 已定义。chat-service 消费 `CircleMemberJoined/Left` 事件。
  - content 域：`Post.circleIds`、`PostCircleDistribution` 已定义。content-service 有 circle-service 消费者权限。
  - S3 对象存储：运维层面需配置，circle-service 通过 runtime/storage 适配器对接。
- 无阻断项。

## 对标输入分析

| 对标 | 借鉴点 | 适用边界 |
|------|--------|----------|
| QQ 群文件 | 文件列表 + 容量限制 + 管理员管理 | 轻量文件共享，不做版本管理 |
| 飞书知识库 | 文件夹组织 + 权限控制 | 权限模型参考，不做在线编辑 |
| Discord 频道 | 事件驱动成员同步 + 群聊自定义 | 松耦合集成，不做语音 |
| 微信群 + 群文件 | 群聊+文件一体化体验 | UX 参考，不做微信生态集成 |

## 方案对比

### L3-1: circle-storage

#### 方案 A（选定）：圈子域内 CircleFile 实体

```
Circle 1:N CircleFile
  ├── _id: ObjectId
  ├── circleId: ObjectId (NOT_NULL)
  ├── parentFolderId: ObjectId (NULLABLE, 支持文件夹嵌套)
  ├── name: string (NOT_NULL)
  ├── type: enum FileType [file, folder]
  ├── mimeType: string (NULLABLE, file 时填充)
  ├── sizeBytes: int64 (NOT_NULL, DEFAULT_0)
  ├── objectKey: string (NULLABLE, S3 key，folder 无)
  ├── uploaderId: string (NOT_NULL)
  ├── status: enum FileStatus [active, deleted]
  ├── createdAt: timestamp
  └── updatedAt: timestamp

Circle 新增字段：
  ├── storageUsedBytes: int64 (当前已用)
  └── storageQuotaBytes: int64 (配额上限)
```

API 设计：
- `GET    /v1/circles/{circleId}/files?parentId=&sort=&cursor=&limit=` — 文件列表
- `POST   /v1/circles/{circleId}/files` — 创建文件夹 / 获取上传 URL
- `GET    /v1/circles/{circleId}/files/{fileId}` — 文件详情 / 下载 URL
- `PATCH  /v1/circles/{circleId}/files/{fileId}` — 重命名
- `DELETE /v1/circles/{circleId}/files/{fileId}` — 删除

上传流程（预签名 URL 模式）：
1. 客户端 `POST /files`（name, mimeType, sizeBytes）→ 服务端验证权限、容量 → 返回 `{fileId, uploadUrl}`
2. 客户端直传 S3（uploadUrl）
3. 客户端 `PATCH /files/{fileId}` 确认上传完成 → 服务端验证 S3 对象存在 → 更新 status=active
4. 服务端更新 Circle.storageUsedBytes

下载流程：
1. 客户端 `GET /files/{fileId}` → 验证权限 → 返回 `{downloadUrl}`（预签名，5 分钟有效）

权限矩阵：
| 角色 | 浏览 | 下载 | 上传 | 重命名 | 删除 |
|------|------|------|------|--------|------|
| owner | ✓ | ✓ | ✓ | ✓ | ✓（全部） |
| admin | ✓ | ✓ | ✓ | ✓（本层级） | ✓（本层级） |
| member | ✓ | ✓ | ✓ | ✗ | ✗ |
| visitor | ✓ | ✓（公开文件） | ✗ | ✗ | ✗ |

**方案 B（备选）**：独立 file-service。不选，理由见 L1 design.md D-3。

### L3-2: circle-group-chat

#### 方案 A（选定）：事件驱动松耦合

```
圈子创建时：
  circle-service.CreateCircle()
    → 发布 CircleCreated 事件
    → chat-service 消费：
        创建 Conversation(type=circle, circleId=xxx, title=圈子名)
        回写 conversationId 到 Circle（通过 CircleConversationLinked 事件）

成员加入时：
  circle-service.JoinCircle()
    → 发布 CircleMemberJoined{circleId, userId}
    → chat-service 消费：
        if circle.autoSyncChat:
          将 userId 加入 Conversation.memberIds

成员退出时：
  circle-service.LeaveCircle()
    → 发布 CircleMemberLeft{circleId, userId}
    → chat-service 消费：
        if circle.autoSyncChat:
          将 userId 从 Conversation.memberIds 移除
```

Circle 新增字段：
- `autoSyncChat: boolean (DEFAULT_TRUE)` — 是否自动同步成员到群聊

端侧群聊入口卡片：
- 从 `Circle.conversationId` 获取群聊 ID
- 调用 chat Repository 获取最近消息 + 未读计数
- 点击跳转到 `/chat/{conversationId}`

群聊自定义（复用 chat-service 已有能力）：
- 修改群名/头像：`PATCH /v1/chat/conversations/{id}`
- 群公告/置顶：chat-service settings 字段

**方案 B（备选）**：同步 RPC。不选，理由见 L1 design.md D-4。

### L3-3: circle-publishing-zone

#### 方案 A（选定）：复用 content 域 + circleId 过滤

圈子 feed 数据流：
```
GetCircleFeed(circleId, cursor, limit, sort)
  → 查询 PostCircleDistribution(circleId=x, state=active)
  → JOIN Post → 按 sort 排序（latest/hot/featured）
  → 返回 Post 列表 + 分页 cursor
```

发帖入口：
- 圈子详情页 FAB → 跳转创作页（`/create?circleIds=[circleId]`）
- 创作页自动填充 circleIds

圈主操作：
- 置顶帖：`PATCH /v1/circles/{circleId}/feed/{postId}/pin` → 更新 PostCircleDistribution.pinned=true
- 精选帖：`PATCH /v1/circles/{circleId}/feed/{postId}/feature` → 更新 PostCircleDistribution.featured=true

Circle service.yaml 新增端点：
- `PATCH /v1/circles/{circleId}/feed/{postId}/pin`
- `PATCH /v1/circles/{circleId}/feed/{postId}/feature`

**方案 B（备选）**：物化投影。不选，理由见 L1 design.md D-5。

## 选型决策

| L3 | 选定方案 | 理由 |
|----|----------|------|
| circle-storage | 圈子域内 CircleFile | 域内聚合最简、权限复用角色模型 |
| circle-group-chat | 事件驱动松耦合 | events.yaml 已就绪、DDD 松耦合 |
| circle-publishing-zone | 复用 content + circleId | PostCircleDistribution 已存在 |

## 关键设计决策

- **DK-1**：文件上传采用预签名 URL 模式（客户端直传 S3），减轻服务端带宽压力。
- **DK-2**：文件容量限制在服务端校验（`sizeBytes + storageUsedBytes > storageQuotaBytes` → 拒绝），不信任客户端。
- **DK-3**：群聊创建由 `CircleCreated` 事件触发（非创建圈子 API 内同步），保证圈子创建 API 的快速返回。
- **DK-4**：`autoSyncChat` 默认 true，圈主可在圈子设置中关闭（`PATCH /v1/circles/{circleId}` 更新）。
- **DK-5**：发布区排序支持三种模式（latest/hot/featured），hot 由 content 域的 PostReaction 计数驱动，featured 由圈主标记。
- **DK-6**：v1 每个圈子仅一个默认群聊（`conversationId` 单值）。多群聊是未来演进。

## Story 与测试层映射

| L4 Story | T1 单元 | T2 集成 | T3 契约 | T4 E2E |
|----------|---------|---------|---------|--------|
| circle-storage-crud-contract | CRUD 单元（创建/上传/下载/删除）| S3 mock 上传下载 | service.yaml 端点对齐 | 上传→下载→删除全流程 |
| circle-chat-integration-contract | 事件发布格式 | chat-svc 消费验证 | events.yaml 一致 | 加入圈子→自动进群 |
| circle-publishing-contract | feed 查询排序 | content 代理查询 | 分页参数契约 | 发帖→圈子 feed 可见 |

## 未来演进

- 存储空间 → 独立 file-service（触发条件：其他域需文件管理）
- 多群聊频道（触发条件：大型圈子需子频道分区讨论）
- 实时协作编辑（触发条件：在线文档需求明确）
- 文件版本管理（触发条件：协作编辑需要版本追溯）

## 遗留带规划任务

- `projections/circle_feed.yaml` 已预留，当圈子 feed 需独立排序优化时启用
- chat-service 需新增对 `CircleCreated` 事件的消费逻辑（创建 circle 类型 Conversation）
