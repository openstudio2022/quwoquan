# 富媒体消息 设计方案

## 设计动因

spec.md 要求在已有语音消息基础设施之上，补齐视频消息和文件消息端到端闭环，修复图片消息发送链路缺陷，并增强 Emoji 体验。核心设计挑战：

1. **统一发送架构**：视频/文件/图片消息共享 `MediaUploadManager → ChatMessageNotifier.sendMessage` 模式，如何避免 3 份重复代码
2. **视频压缩选型**：端侧压缩方案需兼顾压缩效率、包体积和双端兼容性
3. **文件预览策略**：PDF/TXT/MD 端侧原生渲染 vs Office 格式系统打开的路由设计
4. **气泡扩展性**：`chat_message_bubble.dart` 当前用 if-else 链路由消息类型，新增 3 种类型后如何保持可维护性

## 上游输入评审

- **spec.md**：功能范围清晰（F1~F4, 22 项），约束完备（弱网/并发/部署）
- **acceptance.yaml**：A1~A15 可测量，test_layers 已映射
- **阻断项**：无。metadata 不需变更（MessageType/media schema 已覆盖），基础设施已验证
- **补充项**：`UploadPolicy.chatVideo.maxDurationMs` 当前为 300000（5分钟），spec 要求 10 分钟，需更新为 600000

## 对标输入分析

| 对标 | 借鉴点 | 不借鉴点 | 当前差距 | 收敛路径 |
|------|--------|---------|---------|---------|
| 微信视频消息 | 缩略图气泡+时长角标+进度环+全屏播放 | 过度压缩画质、5分钟限制 | 视频消息完全缺失 | 本次实现 |
| 微信文件消息 | 文件卡片+类型图标着色+先下后看 | 200MB 上限 | 文件消息占位发送 | 本次实现 |
| 微信 Office 预览 | WebView 在线预览体验一致 | 依赖在线服务 | 无任何预览能力 | Phase 1 系统打开，Phase 2 云端转换 |
| 微信大号 Emoji | 纯 Emoji 放大显示 | 自定义表情包 | 未实现 | 本次实现 |

## 方案对比

### 方案对比 1：视频压缩引擎

#### 方案 A：`video_compress`（选定）

基于平台原生 API（iOS: AVFoundation, Android: MediaCodec）的轻量压缩库。

**优点**：包体积小（<2MB）；双端原生性能好；支持 720p/1080p/原画质量枚举；内置首帧提取 `getFileThumbnail`；API 简洁（单方法 `compressVideo`）
**缺点**：压缩参数有限（不能精确控制码率/GOP）；不支持音频独立处理
**适用条件**：标准视频压缩需求，不需要复杂转码

#### 方案 B：`ffmpeg_kit_flutter`

完整 FFmpeg 封装，支持任意转码参数。

**优点**：参数完全可控（码率/分辨率/编码器/容器）；可处理任意格式转换
**缺点**：包体积巨大（20~80MB，取决于启用的编解码器）；API 复杂（需拼 CLI 命令）；双端维护成本高；App 增大影响用户下载转化
**适用条件**：需要专业视频处理能力的场景

#### 方案 C：平台原生 Channel

自行编写 iOS/Android 原生压缩代码。

**优点**：完全可控，零外部依赖
**缺点**：开发成本极高；双端各维护一套代码；需要深入 MediaCodec/AVFoundation
**适用条件**：无合适第三方库的极端场景

### 方案对比 2：PDF 阅读器

#### 方案 A：`pdfx`（选定）

基于平台原生 PDF 渲染的 Flutter 插件。

**优点**：MIT 开源无商业限制；支持翻页/缩放/滚动/书签；渲染质量好（原生引擎）；支持本地文件和网络 URL；轻量（无额外引擎）
**缺点**：不支持 PDF 注释编辑
**适用条件**：只读 PDF 查看

#### 方案 B：`syncfusion_flutter_pdfviewer`

Syncfusion 商业级 PDF 查看器。

**优点**：功能最全（注释/搜索/表单填写/书签面板）；企业级支持
**缺点**：商业许可（社区版有限制，>$1000/年的企业版）；包体积大；引入重度依赖
**适用条件**：需要 PDF 编辑/注释的商业应用

#### 方案 C：`flutter_pdfview`

基于 AndroidPdfViewer/PDFKit 的老牌插件。

**优点**：稳定、久经考验
**缺点**：维护不够活跃；API 较旧；缩放体验不如 `pdfx`
**适用条件**：极简 PDF 查看

### 方案对比 3：统一媒体发送架构

#### 方案 A：统一 `MediaSendProvider`（选定）

创建一个统一的 `MediaSendProvider`，封装 upload→send 流程，通过 `MediaCategory` 区分视频/文件/图片。

**优点**：消除重复代码（upload→send 模式统一）；状态管理集中；离线队列共享；与 `VoiceSendProvider` 模式一致但更通用
**缺点**：需设计通用的 `MediaSendRequest` 数据结构；视频压缩等预处理逻辑需前置于统一流程
**适用条件**：多种媒体类型共享相同的 upload→send 模式

#### 方案 B：每种类型独立 Provider

创建 `VideoSendProvider`、`FileSendProvider`、`ImageSendProvider`，各自独立。

**优点**：每种类型的逻辑完全独立，易于理解
**缺点**：3 份几乎相同的 upload→send 代码；离线队列逻辑重复；维护成本线性增长
**适用条件**：各类型有极大差异时

### 方案对比 4：系统文件打开

#### 方案 A：`open_filex`（选定）

`open_file` 的活跃维护分支。

**优点**：最新维护（2024）；支持 iOS/Android 双端；自动根据 MIME 类型选择合适应用；支持自定义 UTI
**缺点**：少量机型兼容性问题
**适用条件**：需要调用系统应用打开文件

#### 方案 B：`open_file`

原始库，较久未更新。

**优点**：API 稳定
**缺点**：最新维护较少；部分 Android 13+ 兼容性问题
**适用条件**：旧项目兼容

### 方案对比 5：保存到相册

#### 方案 A：`gal`（选定）

新一代相册保存库，基于平台 API。

**优点**：轻量；支持 iOS PHPhotoLibrary + Android MediaStore；支持图片和视频；处理权限
**缺点**：社区较新
**适用条件**：保存图片/视频到系统相册

#### 方案 B：`image_gallery_saver`

老牌相册保存库。

**优点**：社区成熟
**缺点**：Android 13+ 需要适配 MediaStore；API 较旧
**适用条件**：兼容旧项目

## 选型决策

| 决策 | 选定 | 理由 |
|------|------|------|
| 视频压缩 | **`video_compress`** | 轻量原生、包体积小、API 简洁、满足 720p 压缩需求 |
| 视频播放器 | **`chewie` + `video_player`**（已安装） | 无需新增依赖，已在发现域使用 |
| 视频缩略图 | **`video_thumbnail`**（已安装） | 与 `video_compress` 互补用于封面提取 |
| PDF 阅读器 | **`pdfx`** | MIT 无商业限制、原生渲染质量好、轻量 |
| Markdown 渲染 | **`flutter_markdown`**（已安装） | 无需新增依赖 |
| 图片查看器 | **`photo_view`**（已安装） | 无需新增依赖，缩放/手势已验证 |
| 系统文件打开 | **`open_filex`** | 活跃维护、双端兼容、自动 MIME 路由 |
| 保存到相册 | **`gal`** | 轻量、支持图片+视频、处理权限 |
| 发送架构 | **统一 `MediaSendProvider`** | 消除重复、共享离线队列、可扩展 |
| Emoji 检测 | **Unicode 正则匹配** | 无需引入新包，`characters` 包做辅助 |

## 关键设计决策

### KD-1: 统一媒体发送架构（已定）

```
┌─────────────────────────────────────────────────────────┐
│                   ChatDetailPage                        │
│  _pickChatImages / _pickChatFiles / _pickChatVideo      │
│               │              │             │            │
│               ▼              ▼             ▼            │
│         ┌─────────────────────────────────────┐         │
│         │        MediaSendProvider            │         │
│         │  ┌──────────────────────────────┐   │         │
│         │  │ 1. 预处理 (压缩/提取封面)    │   │         │
│         │  │ 2. MediaUploadManager.enqueue │   │         │
│         │  │ 3. 监听上传进度/完成/失败    │   │         │
│         │  │ 4. ChatMessageNotifier.send   │   │         │
│         │  │ 5. 离线队列 (共享 Hive box)  │   │         │
│         │  └──────────────────────────────┘   │         │
│         └─────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────┘
```

```dart
class MediaSendRequest {
  final String localPath;
  final MediaCategory category;    // chatVideo / chatFile / chatImage
  final String messageType;        // 'video' / 'file' / 'image'
  final String contentType;        // MIME type
  final int fileSize;
  final String fileName;
  final Map<String, dynamic> mediaMetadata; // width/height/durationMs etc.
  final String? thumbnailPath;     // 视频封面本地路径（video only）
}
```

发送流程：
1. 若有 `thumbnailPath`（视频封面）→ 先上传封面获取 `thumbnailUrl`
2. 上传主文件 → `MediaUploadManager.enqueue`
3. 监听 `onTaskUpdate` → 完成后组装 `media` payload
4. 调用 `ChatMessageNotifier.sendMessage(type, '', mediaUrl: cdnUrl, media: payload)`

### KD-2: 视频压缩与封面提取流程（已定）

```dart
Future<MediaSendRequest> prepareVideo(XFile videoFile) async {
  // 1. 获取视频元数据
  final info = await VideoCompress.getMediaInfo(videoFile.path);
  
  // 2. 校验时长（≤10 分钟 = 600000ms）
  if ((info.duration ?? 0) > 600000) throw '视频时长超过 10 分钟';
  
  // 3. 压缩至 720p
  final compressed = await VideoCompress.compressVideo(
    videoFile.path,
    quality: VideoQuality.Res720pQuality,
    deleteOrigin: false,
  );
  
  // 4. 提取首帧封面
  final thumbnail = await VideoCompress.getFileThumbnail(
    videoFile.path,
    quality: 80,   // JPEG quality
    position: -1,  // 首帧
  );
  
  // 5. 保存封面到临时文件
  final thumbPath = '${(await getTemporaryDirectory()).path}/thumb_${DateTime.now().millisecondsSinceEpoch}.jpg';
  await thumbnail.writeAsBytes(...);
  
  return MediaSendRequest(
    localPath: compressed.path!,
    category: MediaCategory.chatVideo,
    messageType: 'video',
    contentType: 'video/mp4',
    fileSize: compressed.filesize!,
    fileName: videoFile.name,
    mediaMetadata: {
      'width': info.width,
      'height': info.height,
      'durationMs': info.duration?.toInt(),
    },
    thumbnailPath: thumbPath,
  );
}
```

### KD-3: 视频消息气泡设计（已定）

```
┌───────────────────────────────┐
│                               │
│        ┌─────────────┐        │
│        │  缩略图      │        │  宽度: 40%~70% screenWidth
│        │  (圆角裁剪)  │        │  高度: 按原始比例
│        │             │        │
│        │    ▶ 播放    │        │  居中半透明播放图标
│        │             │        │
│        │      01:23 ──│        │  右下角时长角标
│        └─────────────┘        │
│                               │
│  ┌──────────────────────────┐ │  发送中:
│  │ ████████░░░░ 67%         │ │  底部圆环/条形上传进度
│  └──────────────────────────┘ │
└───────────────────────────────┘
```

气泡宽度算法：
```dart
double videoBubbleWidth(int width, int height, double screenWidth) {
  const minRatio = 0.40;
  const maxRatio = 0.70;
  final aspectRatio = width / height;
  final ratio = (minRatio + (maxRatio - minRatio) * 
      (aspectRatio.clamp(0.5, 2.0) - 0.5) / 1.5);
  return screenWidth * ratio;
}
```

### KD-4: 文件消息气泡设计（已定）

```
┌──────────────────────────────────────┐
│  ┌────────┐                          │
│  │  📄    │  项目方案_v3.pdf          │  文件名（单行截断）
│  │  PDF   │  2.4 MB                  │  文件大小
│  │  (红色) │  ████████░░ 67%         │  下载进度（下载中）
│  └────────┘                          │  或 ✓ 已下载（已缓存）
└──────────────────────────────────────┘
```

文件类型图标映射：
```dart
({IconData icon, Color color}) fileTypeVisual(String mimeType, String fileName) {
  final ext = fileName.split('.').last.toLowerCase();
  return switch (ext) {
    'pdf'                          => (Icons.picture_as_pdf, AppColors.error),
    'doc' || 'docx'                => (Icons.description, Color(0xFF3182CE)),
    'ppt' || 'pptx'               => (Icons.slideshow, Color(0xFFDD6B20)),
    'xls' || 'xlsx'               => (Icons.table_chart, AppColors.success),
    'txt' || 'md'                  => (Icons.text_snippet, AppColors.light.textTertiary),
    _                              => (Icons.insert_drive_file, AppColors.light.textTertiary),
  };
}
```

> 注：颜色常量后续需提取到 `AppColors` 设计系统中注册为语义色（如 `AppColors.fileTypeWord`），避免硬编码。

### KD-5: 文件预览路由（已定）

```dart
Future<void> openFilePreview(BuildContext context, String localPath, String mimeType, String fileName) async {
  final ext = fileName.split('.').last.toLowerCase();
  
  switch (ext) {
    case 'pdf':
      Navigator.push(context, CupertinoPageRoute(
        builder: (_) => PdfViewerPage(filePath: localPath, title: fileName),
      ));
    case 'txt':
      Navigator.push(context, CupertinoPageRoute(
        builder: (_) => TextViewerPage(filePath: localPath, title: fileName),
      ));
    case 'md':
      Navigator.push(context, CupertinoPageRoute(
        builder: (_) => MarkdownViewerPage(filePath: localPath, title: fileName),
      ));
    case 'doc' || 'docx' || 'ppt' || 'pptx' || 'xls' || 'xlsx':
      await OpenFilex.open(localPath, type: mimeType);
    default:
      await OpenFilex.open(localPath, type: mimeType);
  }
}
```

### KD-6: 聊天图片全屏查看（已定）

复用已安装的 `photo_view` 包：

```dart
// 点击图片气泡
GestureDetector(
  onTap: () => Navigator.push(context, CupertinoPageRoute(
    builder: (_) => ChatImageViewerPage(
      imageUrls: allImageUrlsInConversation,
      initialIndex: currentIndex,
    ),
  )),
  child: Hero(
    tag: 'chat_image_$messageId',
    child: /* 现有图片气泡 */,
  ),
)
```

`ChatImageViewerPage`：
- `PageView` + `PhotoView` 支持缩放
- 左右滑动切换同会话图片
- 下滑手势关闭（`DismissiblePage` 模式）
- 长按菜单：保存到相册（`gal`）

### KD-7: 大号 Emoji 检测算法（已定）

```dart
bool isPureEmoji(String text) {
  final trimmed = text.trim();
  if (trimmed.isEmpty) return false;
  
  // 移除所有 Emoji 字符和 ZWJ/变体选择符后，应为空
  final withoutEmoji = trimmed.replaceAll(
    RegExp(
      r'[\u{1F600}-\u{1F64F}]|[\u{1F300}-\u{1F5FF}]|[\u{1F680}-\u{1F6FF}]|'
      r'[\u{1F1E0}-\u{1F1FF}]|[\u{2600}-\u{26FF}]|[\u{2700}-\u{27BF}]|'
      r'[\u{FE00}-\u{FE0F}]|[\u{1F900}-\u{1F9FF}]|[\u{1FA00}-\u{1FA6F}]|'
      r'[\u{1FA70}-\u{1FAFF}]|[\u{200D}]|[\u{20E3}]|[\u{FE0F}]|[\u{E0020}-\u{E007F}]',
      unicode: true,
    ),
    '',
  );
  if (withoutEmoji.isNotEmpty) return false;
  
  // 使用 characters 包精确计数
  final graphemeCount = trimmed.characters.length;
  return graphemeCount >= 1 && graphemeCount <= 3;
}
```

显示：`isPureEmoji(content)` 为 true 时，`fontSize` 使用 `AppTypography.display`（≥40）。

### KD-8: 消息气泡类型扩展策略（已定）

当前 `chat_message_bubble.dart` 用 if-else 链路由消息类型。新增 `video`/`file` 分支，增强 `image` 分支：

```
if (type == 'task_card')       → TaskCardBubble (已有)
else if (type == 'video')      → VideoMessageBubble (新增)
else if (type == 'file')       → FileMessageBubble (新增)
else if (type == 'image')      → ImageMessageBubble (重构：加全屏+进度)
else if (type == 'audio')      → VoiceMessageBubble (已有)
else if (isAssistantMessage)   → AssistantBubble (已有)
else                           → TextBubble + 大号 Emoji 检测 (增强)
```

每种气泡独立 Widget 文件：
- `video_message_bubble.dart`
- `file_message_bubble.dart`
- `image_message_bubble.dart`（从内联代码提取为独立 Widget）

### KD-9: 向后兼容策略（已定，沿用语音消息设计）

发送时同时写入 `mediaUrl`（= `media.url`）和 `media` 对象：
- 新客户端优先读 `media` 对象
- 旧客户端读 `mediaUrl`，展示 `[视频消息]` / `[文件] filename` 占位

### KD-10: 视频缓存独立池（已定）

现有 `MediaDownloadCache` 默认 200MB，语音和文件共享。视频由于体积大，需独立缓存池：

```dart
// app_providers.dart
final videoDownloadCacheProvider = Provider<MediaDownloadCache>((ref) {
  return MediaDownloadCache(
    maxCacheBytes: 500 * 1024 * 1024,  // 500MB
    subDir: 'video_cache',
  );
});

final fileDownloadCacheProvider = Provider<MediaDownloadCache>((ref) {
  return MediaDownloadCache(
    maxCacheBytes: 200 * 1024 * 1024,  // 200MB（共享，含语音）
    subDir: 'media_cache',
  );
});
```

### KD-11: 离线队列统一扩展（已定）

现有 `VoiceOfflineQueue`（Hive box: `voice_offline_queue`）扩展为通用 `MediaOfflineQueue`（Hive box: `media_offline_queue`），支持所有媒体类型：

```dart
@HiveType(typeId: 20)
class MediaOfflineItem {
  @HiveField(0) final String localPath;
  @HiveField(1) final String conversationId;
  @HiveField(2) final String clientMsgId;
  @HiveField(3) final String messageType;      // video / file / image
  @HiveField(4) final String contentType;       // MIME
  @HiveField(5) final int fileSize;
  @HiveField(6) final String fileName;
  @HiveField(7) final Map<String, dynamic> mediaMetadata;
  @HiveField(8) final String? thumbnailPath;
  @HiveField(9) final DateTime createdAt;
  @HiveField(10) final String status;           // pending / uploading / failed
  @HiveField(11) final int retryCount;
}
```

网络恢复时 FIFO 处理，与 `VoiceOfflineQueue` 相同逻辑。

## TDD / ATDD 策略

每个 Story 实施时严格 Red→Green→Refactor：

1. **先写验收测试骨架**（A1~A15 对应的测试文件和函数签名，全部标记 `skip`）
2. **逐 task 解除 skip**：实现一个 task → 对应测试转绿 → 重构
3. **T1（契约）先行**：先验证 MessageDto 对 video/file 类型的序列化/反序列化
4. **T2（Widget）次之**：气泡 Widget Golden 测试 + 交互测试
5. **T3（集成）再验**：端云联调 SendMessage + SyncMessages
6. **T4（旅程）最后**：端到端发送→接收→播放/预览旅程

## Story 与测试层映射

| L4 Story | T1 契约 | T2 模块 | T3 集成 | T4 旅程 |
|----------|---------|---------|---------|---------|
| video-message-e2e | MessageDto video 序列化 | 视频压缩+气泡+播放器 Widget | SendMessage(video)+Sync 联调 | 发送→播放旅程 |
| file-message-e2e | MessageDto file 序列化 | 文件气泡+下载+PDF/TXT/MD 预览器 | SendMessage(file)+Sync+下载联调 | 发送→下载→各格式预览旅程 |
| image-message-fix | MessageDto image 序列化 | 图片发送修复+全屏查看器+大号Emoji | SendMessage(image)+Sync 联调 | 发送→全屏查看旅程 |

## 实时性与弱网设计

沿用语音消息策略（KD-9 in voice-message design.md）：

| 场景 | 策略 |
|------|------|
| Phase 1 接收延迟 | HTTP 轮询 ≤8s |
| Phase 2 接收延迟 | WebSocket <500ms |
| 上传弱网 | 重试 ≤3 次指数退避，极弱网/断网入离线队列 |
| 下载弱网 | 缩略图先展；视频/文件手动点击下载；下载超时 30s 显示重试 |
| 非 WiFi | 视频/文件不自动下载（仅显示气泡信息） |
| 断线恢复 | 网络恢复后 MediaOfflineQueue FIFO 自动重传 |

## 并发性能与容量设计

| 指标 | 设计 |
|------|------|
| 并发上传 | MediaUploadManager maxConcurrent=3（已有） |
| 并发下载 | MediaDownloadCache maxConcurrent=4（已有） |
| 视频缓存 | 独立 500MB LRU |
| 文件/语音缓存 | 共享 200MB LRU |
| 离线队列 | ≥50 条，Hive 持久化 |
| 列表性能 | 视频缩略图使用 `CachedNetworkImage`；文件气泡纯文本无网络请求 |

## 灰度发布与回滚设计

同语音消息灰度策略：
- **Phase 1**: integration 全量，A1~A14 全部 implemented
- **Phase 2**: prod 10%，24h 监控 video/file 发送成功率 >99%、播放/预览失败率 <2%、ANR <0.1%
- **Phase 3**: prod 50%，同上监控
- **Phase 4**: prod 100%
- **回滚条件**：任一阶段指标不达标自动回滚

## 适用场景与约束

- **适用**：趣聊 1v1 私聊和群聊中的视频/文件/图片消息端到端
- **约束**：Phase 1 Office 格式依赖用户已安装系统应用（WPS/Office/Pages/Keynote）；视频压缩在老旧低端设备上可能较慢
- **局限**：不含视频编辑、云端格式转换、在线文档预览

## 未来演进

| 演进项 | 触发条件 | 对应搁置任务 |
|--------|---------|------------|
| 云端 Office→PDF 转换 | 用户反馈 Office 预览需求强烈 | E1 |
| WebView 在线文档预览 | 对接华为云/腾讯云文档预览 | E2 |
| 视频分片断点续传 | 大文件上传失败率高 | E3 |
| 多图合并消息 | 单图链路稳定后 | S1 |
| 视频/文件转发 | 消息转发特性启动 | S3 |
| 自定义表情包/贴纸 | 社交互动增强迭代 | E4 |

## 遗留带规划任务

- `UploadPolicy.chatVideo.maxDurationMs` 需从 300000 → 600000（本次交付内变更）
- 文件类型图标颜色需注册到 `AppColors` 设计系统（本次先用临时方案，后续规范化）
- `VoiceOfflineQueue` → `MediaOfflineQueue` 迁移需处理现有 Hive box 兼容

## 补充决策：聊天媒体上传归属（2026-03-08 追加）

### KD-12: chat-service 自建媒体上传 + runtime/media 共性复用（已定）

聊天媒体（图片/视频/文件）上传路由注册在 chat-service 而非 content-service：

**API 路由**（已在 `service.yaml` 中新增）：
- `POST /v1/chat/media/uploads:init` → 获取 presigned URL
- `POST /v1/chat/media/uploads:complete` → 完成上传，返回 CDN URL
- `POST /v1/chat/media/uploads:abort` → 取消上传

**底层复用**：chat-service 注入 `runtime/media.MediaStore` 接口，调用 `InitUpload()/CompleteUpload()/AbortUpload()`，共性的 OSS presign、CDN URL 生成、上传策略校验由 runtime 统一提供。

**端侧**：`MediaUploadManager` 的 `gatewayBaseUrl` 切换到 chat-service 的 `/v1/chat/media/uploads` 路径（原 content-service 的 `/v1/content/media/uploads` 仅用于帖子内容上传）。

**理由**：chat 域媒体与 content 域媒体的生命周期不同（chat 14 天 TTL，content 永久），分别由各自服务管理更清晰。
