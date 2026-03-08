# 富媒体消息（Rich Media Message）

> **层级**：L3_subfeature（隶属 L2 `list-detail-message-delivery`，L1 `chat-conversation`）
> **状态**：specified
> **依赖**：`voice-message`（L3 同级，已实现的媒体消息模板）、`runtime/runtime-media`（统一媒体运行时）

## 背景与动机

趣聊当前的多媒体消息能力不完整：
- **语音消息**（`voice-message`）已完成端到端闭环，建立了 `Message.media` 结构化字段、`MediaUploadManager` 三段式上传、`MediaDownloadCache` LRU 缓存等基础设施
- **图片消息**：`ChatInputAttachmentType.image` 选择器已存在，但 `_submitChatInput` 将图片降级为 `type=text` 文本占位发送，未调用 `MediaUploadManager` 上传；聊天图片无全屏查看
- **视频消息**：`MessageType.video` 已在 metadata 定义，`UploadPolicy.chatVideo`（100MB, mp4/mov）已配置，但端侧完全未实现
- **文件消息**：`MessageType.file` 已在 metadata 定义，`UploadPolicy.chatFile`（100MB）已配置，`FilePicker` 选择器存在但同样降级为文本占位发送；无任何文档预览能力

**核心缺口**：metadata 和基础设施层已就绪，端侧发送链路（选择→上传→发送）和接收展示层（气泡→预览/播放）未打通。

本特性补齐视频消息和文件消息的端到端闭环，并修复图片消息发送链路缺陷，实现从发送到云端同步到各接收方推送、再到接收后点击播放/浏览的完整体验。同时增强 Emoji 体验（大号 Emoji 展示）。

## 目标用户

- **趣聊用户**：所有使用趣聊聊天功能的用户（1v1 私聊和群聊）
- **文件分享者**：需要在聊天中分享 PDF、Office 文档、文本文件等的用户

## 功能范围

### F1 视频消息端到端（L4: `video-message-e2e`）

1. **视频选择**：从相册选择视频或调用相机录制
2. **视频预处理**：端侧压缩至 720p/30fps（默认），提取首帧封面缩略图，获取元数据（宽高/时长/大小）
3. **上传**：封面图 + 视频文件分别通过 `MediaUploadManager` 上传 OSS，获取 CDN URL
4. **发送**：`sendMessage(type='video', media={url, thumbnailUrl, width, height, durationMs, mimeType, fileSizeBytes})`
5. **本地乐观展示**：发送方立即展示缩略图气泡 + 上传进度环
6. **云端存储与推送**：MongoDB 存储消息（含 media 字段），通过 `MessageSent` 事件推送/同步到接收方
7. **视频消息气泡**：缩略图 + 播放按钮 + 时长角标（mm:ss）；圆角裁剪；宽度自适应（最小 40%/最大 70% 屏宽）
8. **点击播放**：下载视频到本地缓存 → 全屏播放器（支持暂停/拖动/横竖屏）
9. **弱网/离线**：上传失败自动重试 ≤3 次；断网入离线队列；接收方缩略图先展示，视频延迟加载

### F2 文件消息端到端（L4: `file-message-e2e`）

10. **文件选择**：`FilePicker` 选择任意格式文件
11. **文件校验**：大小 ≤100MB，获取 fileName/mimeType/fileSizeBytes
12. **上传**：通过 `MediaUploadManager` 上传 OSS
13. **发送**：`sendMessage(type='file', media={url, fileName, mimeType, fileSizeBytes})`
14. **文件消息气泡**：文件类型图标（按格式着色）+ 文件名 + 大小 + 下载/已下载状态
15. **点击操作**：先下载到本地缓存 → 根据文件类型路由到对应预览器
16. **文件预览能力**：
    - **PDF**：端侧原生 PDF 阅读器（翻页/缩放/书签）
    - **TXT**：原生文本查看器（支持 UTF-8/GBK 编码检测）
    - **MD**：Markdown 渲染器
    - **DOCX/DOC/PPTX/PPT**：Phase 1 调用系统应用打开（WPS/Office/Pages/Keynote）；Phase 2 云端转 PDF 后统一预览
17. **弱网/离线**：上传入离线队列；下载显示进度条；下载失败可重试

### F3 图片消息发送修复（L4: `image-message-fix`）

18. **修复发送链路**：图片选择/拍照后通过 `MediaUploadManager` 上传，以 `type='image'` + `media={url, thumbnailUrl, width, height, mimeType, fileSizeBytes}` 发送（替代当前文本占位）
19. **聊天图片全屏查看**：点击图片气泡转场至全屏图片查看器（缩放/滑动切换/保存到相册）
20. **多图发送**：支持一次选择多张图片，逐张上传发送（复用 `media.items[]` 后续增强）

### F4 Emoji 体验增强

21. **大号 Emoji**：纯 Emoji 消息（1~3 个 Emoji，无文字）放大显示（fontSize 从默认 16 放大到 40）
22. **Emoji 输入**：现有 `UnifiedEmojiPicker` 已完整，无需修改

## 不做什么（Out of Scope）

- **云端视频转码**：Phase 1 不做云端转码，端侧压缩即可
- **云端文档转换**：Phase 1 Office 格式通过系统应用打开，不做 LibreOffice/UNOCONV 云端转 PDF
- **在线文档预览**：不对接第三方在线预览服务（如华为云文档预览）
- **视频编辑**：不实现裁剪/滤镜/贴纸等视频编辑功能
- **自定义表情包/贴纸**：需要新建表情包管理系统，不在本次
- **GIF 搜索发送**：需对接 GIF 服务，不在本次
- **消息反应（表情回复）**：需要新增消息反应模型，不在本次
- **文件在线编辑**：不在本次
- **WPS 专有格式（.wps/.dps）**：已淘汰格式，WPS 当前默认保存为 .docx/.pptx
- **断点续传**：Phase 1 整文件重传，Phase 2 评估分片断点续传

## 约束

### 技术约束

- 视频/文件/图片上传必须通过 `MediaUploadManager`（OSS presign → 直传 → complete），禁止绕过
- 发送必须通过 `ChatRepository.sendMessage(type=video/file/image)`，禁止降级为 text
- 视频压缩使用 `video_compress` 或 `ffmpeg_kit_flutter`，输出 mp4/H.264
- 文件预览 PDF 使用 `pdfx` 或 `syncfusion_flutter_pdfviewer`
- Markdown 渲染使用 `flutter_markdown` 或 `markdown_widget`
- 所有气泡 UI 使用 `AppTypography`/`AppSpacing`/`AppColors`，禁止硬编码
- metadata 不需要变更（`MessageType` 已含 video/file/image，`Message.media` schema 已覆盖）

### 业务约束

| 消息类型 | 大小上限 | 格式限制 | 时长/页数限制 |
|---------|---------|---------|-------------|
| 视频 | 100MB | mp4, mov | 10 分钟 |
| 文件 | 100MB | 无限制 | — |
| 图片 | 20MB | jpeg, png, gif, webp, heic | — |

### 弱网与性能约束

| 场景 | 视频消息 | 文件消息 | 图片消息 |
|------|---------|---------|---------|
| 强网上传延迟 | 30MB 视频 ≤5s | 10MB 文件 ≤3s | 5MB 图片 ≤2s |
| 弱网（100kbps） | 入离线队列 + 重试3次 | 入离线队列 + 重试3次 | 入离线队列 + 重试3次 |
| 断网 | 本地暂存 + ⏳ 待发送 | 本地暂存 + ⏳ 待发送 | 本地暂存 + ⏳ 待发送 |
| 接收方弱网 | 缩略图先展，视频手动下载 | 气泡显示文件信息，手动下载 | 缩略图先展，原图手动加载 |
| 接收播放/预览延迟 | 缓存命中 <1s，首次 <5s | 缓存命中 <1s，首次 <5s | 缓存命中即时，首次 <2s |

### 实时性约束

| 指标 | Phase 1（HTTP 轮询） | Phase 2（WebSocket） |
|------|---------------------|---------------------|
| 发送方感知延迟（含上传） | 视频 ≤5s / 文件 ≤3s / 图片 ≤2s | 同 Phase 1 |
| 接收方感知延迟 | ≤8s（含 5s 轮询间隔） | ≤1s |
| 缩略图可见延迟 | 同消息到达 | 同消息到达 |

### 并发性能约束

| 指标 | 要求 |
|------|------|
| 并发上传 | 最多 3 个同时上传（MediaUploadManager 已支持） |
| 离线队列容量 | ≥50 条待发送媒体消息 |
| 视频本地缓存 | 独立 500MB LRU 池 |
| 文件本地缓存 | 共享 200MB LRU 池（同语音） |
| 聊天列表含媒体气泡 | 滚动 60fps 无卡顿 |

### 部署约束

- 端侧通过 App Store / Google Play 发布，支持 iOS 15+ / Android API 26+
- 云侧 metadata 不需要变更（video/file/image 类型已在 `_shared/types.yaml` 和 `fields.yaml` 中定义）
- 灰度发布策略同语音消息：integration 全量 → prod 10% → 50% → 100%

## 适用范围与约束

- **适用场景**：趣聊 1v1 私聊和群聊中发送/接收视频消息和文件消息，以及修复图片消息发送缺陷
- **前置条件**：`MediaUploadManager` 已实现并在语音消息中验证通过；`UploadPolicy` 已定义 chatVideo/chatFile/chatImage
- **不适用**：超大文件传输（>100MB）、视频编辑/剪辑、Office 格式原生渲染（Phase 1 走系统应用）、E2EE 加密传输

## 对标输入与吸收结论

### 视频消息对标（微信）

| 对标 | 借鉴点 | 不借鉴点 | 适用边界 |
|------|--------|---------|---------|
| **微信** | 缩略图气泡+时长角标+播放图标；点击全屏播放；发送进度环；弱网缩略图先展；视频下载后可保存到相册 | 5 分钟时长限制（我们用 10 分钟）；过度压缩画质差 | 交互范式成熟，直接对标 |
| **Telegram** | 自动播放 GIF 式预览 | 自动播放耗流量，不借鉴 Phase 1 | 后续可选增强 |
| **WhatsApp** | 离线队列 + 网络恢复自动重传 | E2EE 复杂度 | 离线策略参考 |

### 文件消息对标（微信）

| 对标 | 借鉴点 | 不借鉴点 | 适用边界 |
|------|--------|---------|---------|
| **微信** | 文件气泡（图标+文件名+大小+来源标签）；类型图标颜色体系（PDF红/Word蓝/PPT橙/文件灰）；点击先下后看；进度条下载 | 200MB 上限（我们用 100MB 更保守） | 文件气泡 UI 直接对标 |
| **微信** | Office 格式 WebView 在线预览 | Phase 1 不做在线预览，走系统打开 | Phase 2 可借鉴 |
| **钉钉** | 文件卡片含预览缩略图 | 过于复杂的预览缩略图生成 | 后续增强 |
| **飞书** | 云文档在线编辑 | 远超当前范围 | 不适用 |

### Emoji 对标（微信）

| 对标 | 借鉴点 | 不借鉴点 | 适用边界 |
|------|--------|---------|---------|
| **微信** | 纯 Emoji 消息放大显示（1-3个） | 自定义表情包系统（后续独立特性） | 大号 Emoji Phase 1 实现 |
| **微信** | Emoji 面板分类浏览 | — | 已实现 ✅ |

## 子节点结构

| L4 Story | 职责 | 交付边界 |
|---------|------|---------|
| `video-message-e2e` | 视频选择→压缩→上传→发送→气泡→播放全链路 | F1 (1-9) |
| `file-message-e2e` | 文件选择→上传→发送→气泡→下载→预览全链路 | F2 (10-17) |
| `image-message-fix` | 图片发送链路修复 + 全屏查看 + 大号Emoji | F3 (18-20) + F4 (21) |

## 验收重点

### T1 契约与静态层

- metadata 不需要变更（video/file/image 已在 types.yaml 和 fields.yaml 中定义）
- 视觉语义检查：`verify_dart_semantic.py` 无新增硬编码

### T2 模块与交互层

- 视频气泡 Widget 渲染正确（缩略图/播放按钮/时长/进度）
- 文件气泡 Widget 渲染正确（图标/文件名/大小/下载状态）
- PDF 阅读器 / TXT 查看器 / MD 渲染器组件独立可测
- 大号 Emoji 检测与放大逻辑正确
- 图片全屏查看器缩放/手势正确

### T3 端云集成层

- 视频/文件/图片消息 `SendMessage` + `SyncMessages` 端云联调
- 上传→发送→同步→下载→预览/播放链路联通

### T4 端到端旅程层

- 视频消息发送→接收→播放旅程
- 文件消息发送→接收→各格式预览旅程
- 图片消息发送→接收→全屏查看旅程
- 弱网/断网发送与恢复旅程

详细验收标准见 `acceptance.yaml`。
