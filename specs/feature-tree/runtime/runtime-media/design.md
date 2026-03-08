# 统一媒体运行时 设计方案

## 设计动因

spec.md 要求提取 `runtime/media` 作为横切基础设施模块。当前媒体处理分散在 content-service（内存 mock）、circle-service（FileStore）、chat-service（无上传能力）三处。语音消息、图片消息等多个特性 block 在缺乏统一上传基础设施上。

## 上游输入评审

- spec.md 清晰，功能范围 9 条明确
- acceptance.yaml A1-A8 全部可测量
- 无阻断项

## 对标输入分析

| 对标 | 借鉴 | 不借鉴 | 当前差距 |
|------|------|--------|---------|
| AWS S3 SDK | presigned URL 模式、三段式（init/upload/complete） | multipart 分片（单文件 ≤500MB 不需要） | 当前无 OSS 集成 |
| 七牛云上传策略 | Token 包含限制条件（大小/类型/过期） | 供应商锁定 | 当前策略硬编码在 content-service |
| 微信媒体管线 | 分层：上传层/处理层/分发层 | 自研 CDN | 当前三层均未实现 |

## 方案对比

### 方案 A：Per-Domain 媒体（现状延续）

各服务各自实现上传逻辑：content-service 保留现有实现，chat-service 新增独立上传端点。

**优点**：改动最小，各域独立演进
**缺点**：重复代码（OSS 配置、presigned URL 生成、CDN 签名、错误处理、可观测性全部重复）；新域接入成本高；策略不一致风险
**适用条件**：仅 1 个域需要媒体上传

### 方案 B：统一 runtime/media 模块（选定）

在 `runtime/media/` 定义 `MediaStore` 接口 + OSS 适配器 + 策略引擎，各服务 import 后注入使用。

**优点**：统一接口、统一策略、统一可观测、统一治理；新域零成本接入；与现有 runtime 模块模式一致
**缺点**：需要 content-service 迁移（风险可控，行为不变）；跨域共享模块的版本管理
**适用条件**：≥2 个域需要媒体上传（当前 3 个域）

### 方案 C：独立 Media 微服务

部署独立的 media-service，各域通过 HTTP/gRPC 调用。

**优点**：完全解耦；可独立扩缩容
**缺点**：增加网络跳数和延迟（每次上传多一次 RPC）；运维成本高；当前规模不需要
**适用条件**：超大规模（日均上传 >100 万次）、需要独立扩缩容

## 选型决策

**选定方案**：方案 B — 统一 runtime/media 模块

**理由**：
1. 3 个域均需媒体上传，重复代码不可接受
2. 完美对齐现有 runtime 模块模式（接口 + 实现 + observability + governance）
3. 避免微服务开销，当前规模不需要独立进程
4. content-service 迁移风险可控——API 路由不变，仅内部实现替换

## 关键设计决策

### KD-1: MediaStore 接口设计（已定）

```go
type MediaStore interface {
    InitUpload(ctx, InitUploadOpts) (*UploadSession, error)
    CompleteUpload(ctx, sessionID string) (*MediaAsset, error)
    AbortUpload(ctx, sessionID string) error
    GetAsset(ctx, mediaID string) (*MediaAsset, error)
    BatchGetAssets(ctx, ids []string) ([]*MediaAsset, error)
}
```

`InitUploadOpts` 含 `Category`（messaging/content/circle）驱动策略路由。

### KD-2: 上传策略引擎（已定）

策略按 Category×MediaType 配置，存储在 `RuntimeConfigProvider`，支持热更新。默认策略：

| Category | MediaType | MaxSize | MaxDuration | AllowedMime |
|----------|-----------|---------|-------------|-------------|
| messaging | audio | 5MB | 120s | audio/aac, audio/mp4 |
| messaging | image | 10MB | — | image/jpeg, image/png, image/webp, image/gif |
| messaging | video | 50MB | 300s | video/mp4, video/quicktime |
| content | video | 500MB | 600s | video/mp4, video/quicktime |
| content | image | 20MB | — | image/jpeg, image/png, image/webp |

### KD-3: OSS Bucket 分区策略（已定）

```
{env}-quwoquan-media/
├── messaging/     # 消息媒体（短生命周期，90 天后降为低频存储）
├── content/       # 内容创作（长期存储）
└── circle/        # 圈子文件（长期存储）
```

单 bucket + prefix 分区（而非多 bucket），简化 CDN 配置。

### KD-4: CDN URL 签名策略（已定）

- 使用带签名的 URL（防盗链）
- messaging 类别签名有效期 7 天（消息媒体生命周期较长但不需永久）
- content 类别签名有效期 1 年
- 客户端缓存时使用 mediaId 作为缓存 key，签名过期后重新获取 URL

### KD-5: 端侧 MediaUploadManager 设计（已定）

- 全局单例，Riverpod Provider 注入
- 内部维护上传队列（PriorityQueue，messaging 优先于 content）
- 并发限制 3 个（Semaphore）
- 重试策略：3 次指数退避（1s→2s→4s）
- 离线队列：Hive Box 持久化，NetworkConnectivity 监听恢复
- 进度回调：StreamController 广播

### KD-6: 端侧 MediaDownloadCache 设计（已定）

- LRU 缓存，容量 200MB（可配置）
- 缓存目录：`getApplicationCacheDirectory()/media_cache/`
- 缓存 key：mediaId（不是 URL，避免签名变更导致 cache miss）
- 下载队列：并发 5 个
- 流式播放支持：返回 File path 供 just_audio 加载

## 适用场景与约束

- **适用**：所有需要持久化存储的媒体文件，file size ≤ 500MB
- **不适用**：实时流媒体（WebRTC）、超大文件（需 multipart）
- **局限**：单一 OSS 供应商；无自动转码管线（后续演进）

## Story 与测试层映射

| Story (L4) | T1 契约 | T2 模块 | T3 集成 | T4 旅程 |
|------------|---------|---------|---------|---------|
| upload-session-and-cdn-delivery | 接口编译+策略 codegen | MockMediaStore+Manager 单测 | OSS 端到端+CDN 签名 | content 迁移+端侧上传 |

## 未来演进

1. **媒体处理管线**：转码、缩略图生成、波形提取（触发条件：content 域需要视频转码时）
2. **多云 OSS**：OSS 适配器抽象允许切换供应商（触发条件：业务需多云部署时）
3. **分片上传**：对 >500MB 文件支持 multipart（触发条件：视频创作支持超长视频时）
4. **CDN 智能路由**：根据用户地理位置选择最近 CDN 节点（触发条件：用户覆盖多区域时）

## 遗留带规划任务

- 媒体审核管线（内容安全扫描）：待内容安全供应商对接后启动
- OSS 生命周期管理（messaging 90 天降频、aborted 会话清理）：待运维基础设施就绪后启动
