# 富媒体消息 任务清单

> **顺序原则**：共享基础设施 → 测试骨架 → 图片修复（最简链路验证） → 视频消息 → 文件消息 → 集成测试

## 当前交付任务

### Phase 0：共享基础设施与依赖

- [ ] P0-1: [依赖] 添加新包到 pubspec.yaml：`video_compress`、`pdfx`、`open_filex`、`gal`
- [ ] P0-2: [代码] 更新 `UploadPolicy.chatVideo.maxDurationMs` 从 300000 → 600000（10 分钟）
- [ ] P0-3: [代码] 创建 `MediaSendProvider`（统一媒体发送 Notifier：预处理→上传→发送→离线队列）
- [ ] P0-4: [代码] 创建 `MediaOfflineQueue`（通用离线队列，替代/扩展 VoiceOfflineQueue，Hive box: media_offline_queue）
- [ ] P0-5: [代码] 注册 `videoDownloadCacheProvider`（独立 500MB LRU）到 `app_providers.dart`
- [ ] P0-6: [测试骨架] 创建 T1/T2 测试文件骨架（全部 skip），为后续逐步解除 skip 做准备

### Story 1：图片消息修复（image-message-fix）—— 最简链路验证

- [ ] I1: [Red] 编写 MessageDto image 类型契约测试（T1，verify fromMap/toMap with media fields）
- [ ] I2: [Green] 修复 `_submitChatInput` 中图片附件发送链路：image 选择/拍照 → `MediaSendProvider.send(category=chatImage)` → `sendMessage(type='image', media={...})`；移除文本占位逻辑
- [ ] I3: [Red] 编写 `ChatImageViewerPage` Widget 测试（T2，缩放/滑动/关闭手势）
- [ ] I4: [Green] 创建 `ChatImageViewerPage`（`photo_view` + `PageView` + Hero 转场 + 下滑关闭）
- [ ] I5: [Green] 增强 `chat_message_bubble.dart` 中 `type == 'image'` 分支：(a) 从 `media` 字段读取 URL；(b) 点击打开 `ChatImageViewerPage`；(c) 发送中显示上传进度
- [ ] I6: [Green] 提取 `ImageMessageBubble` 为独立 Widget 文件
- [ ] I7: [Red] 编写大号 Emoji 检测单元测试（T2，纯 Emoji/混合/空字符串/4+ Emoji）
- [ ] I8: [Green] 实现 `isPureEmoji()` 工具函数 + 文本气泡中大号 Emoji 显示逻辑
- [ ] I9: [Refactor] 长按保存到相册功能（`gal` 包）
- [ ] I10: [验证] `verify_dart_semantic.py` 无新增硬编码

### Story 2：视频消息端到端（video-message-e2e）

- [ ] V1: [Red] 编写 MessageDto video 类型契约测试（T1，verify media fields: url/thumbnailUrl/width/height/durationMs/mimeType/fileSizeBytes）
- [ ] V2: [Red] 编写 `VideoMessageBubble` Widget 测试（T2，缩略图/播放图标/时长角标/进度环）
- [ ] V3: [Green] 实现视频选择 UI（ImagePicker video mode + camera 录制），集成时长校验（≤10 分钟）
- [ ] V4: [Green] 实现视频压缩与封面提取（`video_compress` → 720p/H.264 + 首帧 JPEG）
- [ ] V5: [Green] 实现视频上传链路：封面上传 → 视频上传 → `MediaSendProvider.send(category=chatVideo, thumbnailPath=...)`
- [ ] V6: [Green] 创建 `VideoMessageBubble` Widget（缩略图气泡 + 播放图标 + 时长角标 + 进度环）
- [ ] V7: [Green] 添加 `type == 'video'` 分支到 `chat_message_bubble.dart`
- [ ] V8: [Green] 创建 `ChatVideoPlayerPage`（全屏播放器：`chewie` + 下载→缓存→播放 + 横竖屏）
- [ ] V9: [Green] 实现视频下载与缓存（`videoDownloadCacheProvider`，点击气泡 → 下载 → 播放）
- [ ] V10: [Green] 非 WiFi 环境不自动下载视频（显示"点击下载"按钮）
- [ ] V11: [Refactor] 视频消息弱网/离线处理（MediaOfflineQueue 集成）
- [ ] V12: [验证] `verify_dart_semantic.py` 无新增硬编码

### Story 3：文件消息端到端（file-message-e2e）

- [ ] F1: [Red] 编写 MessageDto file 类型契约测试（T1，verify media fields: url/fileName/mimeType/fileSizeBytes）
- [ ] F2: [Red] 编写 `FileMessageBubble` Widget 测试（T2，类型图标/文件名/大小/下载状态/进度条）
- [ ] F3: [Green] 修复 `_submitChatInput` 中文件附件发送链路：file 选择 → `MediaSendProvider.send(category=chatFile)` → `sendMessage(type='file', media={...})`
- [ ] F4: [Green] 创建 `FileMessageBubble` Widget（文件类型图标着色 + 文件名 + 大小 + 下载状态/进度条）
- [ ] F5: [Green] 添加 `type == 'file'` 分支到 `chat_message_bubble.dart`
- [ ] F6: [Green] 实现文件下载管理（`fileDownloadCacheProvider` + 进度回调 + 重试按钮）
- [ ] F7: [Green] 创建 `PdfViewerPage`（`pdfx` 包，翻页/缩放/滚动）
- [ ] F8: [Green] 创建 `TextViewerPage`（Text Widget + UTF-8/GBK 编码检测）
- [ ] F9: [Green] 创建 `MarkdownViewerPage`（`flutter_markdown` 渲染）
- [ ] F10: [Green] 实现文件预览路由 `openFilePreview()`（PDF→PdfViewer / TXT→TextViewer / MD→MarkdownViewer / Office→`open_filex` / 其他→系统分享）
- [ ] F11: [Green] 文件消息弱网/离线处理（MediaOfflineQueue 集成）
- [ ] F12: [验证] `verify_dart_semantic.py` 无新增硬编码

### Phase 4：集成测试与端云一致性

- [ ] T1: [T3 集成] 编写端云联调测试：SendMessage(type=video/file/image) + SyncMessages 正确同步
- [ ] T2: [T1 静态] 编写端云消息一致性测试：type + media 字段发送方与接收方一致
- [ ] T3: [T1 静态] 编写过往版本客户端 fallback 测试：mediaUrl 占位展示
- [ ] T4: [T2 模块] 编写 MediaSendProvider 单元测试（上传成功/失败/重试/离线队列）
- [ ] T5: [T2 模块] 编写 MediaOfflineQueue 测试（持久化/FIFO/网络恢复/重试上限）
- [ ] T6: [综合] 全量运行 `flutter test test/cloud/chat/ test/ui/chat/`，确保无回归

## 搁置任务（带规划）

- [ ] S1: 多图合并消息（`media.items[]` 多图）—— 需设计多图气泡 Gallery UI 和 items 批量上传策略（重启条件：本次单图链路验证稳定后，由 rich-media-message 节点承接）
- [ ] S2: 视频封面 GIF 预览 —— 需评估移动网络流量和端侧渲染性能开销（重启条件：体验优化迭代时，由 video-message-e2e 节点承接）
- [ ] S3: 视频/文件消息转发 —— 需设计消息转发链路、权限模型和转发计数（重启条件：消息转发特性启动时，由 list-detail-message-delivery 下新建 L3 承接）
- [ ] S4: 文件消息过期策略 —— 需 CDN 过期回收 + 端侧过期提示 UI + 服务端定时任务（重启条件：存储成本优化时，由 file-message-e2e 节点承接）
- [ ] S5: 文件类型图标颜色注册到 AppColors 设计系统 —— 需 UI 设计师确认色值（重启条件：设计系统迭代时）

## 未来演进任务

- [ ] E1: 云端 Office→PDF 转换（LibreOffice Headless），统一文档预览体验（Phase 2，前置：部署 LibreOffice 容器 + 转换服务 API）
- [ ] E2: WebView 在线文档预览（对接华为云/腾讯云文档预览服务）（Phase 3，前置：云服务商对接）
- [ ] E3: 视频分片断点续传（Phase 2，前置：MediaUploadManager 支持 multipart/分片）
- [ ] E4: 自定义表情包/贴纸系统（独立 L3 特性，前置：表情包管理服务 + 端侧商店 UI）
- [ ] E5: GIF 搜索发送（独立 L3 特性，前置：GIF 服务对接 Giphy/Tenor API）
- [ ] E6: 消息反应/表情回复（独立 L3 特性，前置：消息反应数据模型 + 实时推送）
- [ ] E7: 非 WiFi 环境自适应压缩策略（分辨率/码率根据网络质量动态调整）
