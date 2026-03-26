# L2 圈子协作工具 — 任务列表

## 当前交付任务

> 状态同步（2026-03-26）
> - 已完成：群组内核 metadata、`circleGroupId/groupId/nodeId` codegen 基线，以及 `SectionChat/SectionStorage` 的基础端侧壳层。
> - 进行中：`CircleGroup` 与 `Conversation` 的解耦收口。
> - 未完成：`CircleGroup` HTTP 全链路、申请入群、私有群搜索、群资料/公告绑定。

### L3: circle-storage

- [ ] T1: [metadata] 在 `contracts/metadata/social/circle/fields.yaml` 新增 CircleFile 实体（_id, circleId, parentFolderId, name, type, mimeType, sizeBytes, objectKey, uploaderId, status, createdAt, updatedAt）
- [ ] T2: [metadata] 在 Circle 实体新增 `storageUsedBytes`（int64）和 `storageQuotaBytes`（int64）字段
- [ ] T3: [metadata] 在 `service.yaml` 新增 5 个存储 API 端点（ListFiles, CreateFile, GetFile, UpdateFile, DeleteFile）
- [ ] T4: [metadata] 在 `events.yaml` 新增 CircleFileUploaded、CircleFileDeleted 事件
- [ ] T5: [metadata] 在 `errors.yaml` 新增存储错误码（storage_quota_exceeded, file_not_found, file_upload_failed, file_type_not_allowed）
- [ ] T6: [metadata] 在 `storage.yaml` 新增 circle_files collection + 索引定义
- [ ] T7: [codegen] make verify-metadata && make codegen && make codegen-app
- [ ] T8: [业务逻辑-云侧] 实现存储 CRUD API（含预签名 URL 上传/下载、容量校验、权限校验）
- [ ] T9: [业务逻辑-云侧] 实现 S3 适配器（runtime/storage 接口 + AWS S3 实现）
- [ ] T10: [业务逻辑-端侧] 实现 SectionStorage widget：文件列表（图标+名称+大小+日期）、文件夹导航、上传按钮
- [ ] T11: [业务逻辑-端侧] 实现文件上传流程：选择文件 → 获取预签名 URL → 直传 S3 → 确认完成
- [ ] T12: [业务逻辑-端侧] 实现文件下载流程：获取预签名 URL → 浏览器/系统下载器
- [ ] T13: [业务逻辑-端侧] CircleRepository 增加存储相关方法（listFiles, createFile, getFile, updateFile, deleteFile）
- [ ] T14: [测试] 云侧契约测试：存储 API 端点与 service.yaml 一致
- [ ] T15: [测试] 端侧 Widget 测试：SectionStorage 渲染、上传进度、容量提示

### L3: circle-group-chat

- [ ] T16: [metadata] 在 Circle 实体新增 `autoSyncChat`（boolean, DEFAULT_TRUE）字段
- [ ] T17: [metadata] 在 `events.yaml` 中 CircleCreated 事件添加 chat-service 为消费者（已有，确认 conversationId 回写事件）
- [ ] T18: [metadata] 新增 `CircleConversationLinked` 事件（chat-service → circle-service，携带 conversationId）
- [ ] T19: [codegen] make verify-metadata && make codegen && make codegen-app
- [ ] T20: [业务逻辑-云侧] chat-service 消费 CircleCreated 事件：创建 Conversation(type=circle, circleId, title)
- [ ] T21: [业务逻辑-云侧] chat-service 发布 CircleConversationLinked 事件 → circle-service 消费：更新 Circle.conversationId
- [ ] T22: [业务逻辑-云侧] chat-service 消费 CircleMemberJoined/Left 事件：同步成员（检查 autoSyncChat）
- [ ] T23: [业务逻辑-端侧] 实现 SectionChat widget：群聊入口卡片（最近消息预览 + 未读计数 + 跳转）
- [ ] T24: [业务逻辑-端侧] 圈子设置页增加「自动同步群聊成员」开关
- [ ] T25: [测试] 集成测试：加入圈子 → 事件发布 → 群聊成员同步

### L3: circle-publishing-zone

- [ ] T26: [metadata] 在 `service.yaml` 新增 2 个 feed 管理端点（PinPost, FeaturePost）
- [ ] T27: [codegen] make verify-metadata && make codegen
- [ ] T28: [业务逻辑-云侧] 实现 GetCircleFeed：查询 PostCircleDistribution → JOIN Post → 排序（latest/hot/featured）
- [ ] T29: [业务逻辑-云侧] 实现 PinPost / FeaturePost：更新 PostCircleDistribution.pinned/featured
- [ ] T30: [业务逻辑-端侧] 实现 SectionWorks widget：瀑布流+列表视图切换 + 排序选择（最新/最热/精选）
- [ ] T31: [业务逻辑-端侧] 圈子详情页 FAB → 跳转创作页（自动填充 circleId）
- [ ] T32: [测试] 契约测试：feed 分页参数、排序参数与 service.yaml 一致

## 搁置任务

- [ ] 文件版本管理（重启条件：协作编辑需求明确）
- [ ] 多群聊频道管理（重启条件：大型圈子需子频道需求确认）
- [ ] 视频/音频在线预览（重启条件：媒体播放器能力就绪）

## 未来演进任务

- [ ] 存储空间抽取为独立 file-service
- [ ] 物化 circle_feed 投影（projections/circle_feed.yaml）
- [ ] 实时协作文档编辑
