# 统一媒体运行时（runtime-media）

> **层级**：L2_feature（隶属 L1 `runtime`）
> **状态**：specified

## 背景与动机

当前媒体处理分散在三个域中：content-service 内部实现 `InitMediaUpload/CompleteMediaUpload`（内存 mock，未接真实 OSS）；circle-service 独立实现 `FileStore`；chat-service 无媒体上传能力，`Message.mediaUrl` 字段存在但无上传链路。三处各自为政，缺乏统一的 OSS 抽象、CDN 管理、上传策略和可观测性。

语音消息、图片消息、视频消息、文件消息等功能均依赖可靠的媒体上传/存储/分发基础设施。同时，即将落地的实时音视频通话功能虽然流媒体不经 OSS，但信令中携带的媒体元数据、设备管理能力也需统一。

本特性提取 `runtime/media` 作为横切基础设施模块，供 content、chat、circle 三域统一消费，避免重复建设，降低维护成本。

## 目标用户

- **服务开发者**：content-service、chat-service、circle-service 的开发者，通过 `MediaStore` 接口完成媒体上传/存储/查询
- **端侧开发者**：通过统一 Media SDK（`lib/cloud/media/`）完成上传、下载、缓存
- **最终用户**：间接受益——媒体上传更快、更可靠、弱网体验更好

## 功能范围

1. **MediaStore 接口**：定义 `InitUpload` → `CompleteUpload` → `AbortUpload` → `GetAsset` → `BatchGetAssets` 的统一接口
2. **OSS 适配器**：实现 presigned URL 上传（PUT），支持华为云 OBS / S3 兼容存储
3. **CDN URL 签名**：上传完成后生成带签名的 CDN URL，支持过期策略
4. **上传策略引擎**：按 `MediaCategory`（messaging/content/circle）× `MediaType`（image/video/audio/file）定义大小限制、时长限制、格式白名单，策略可配置
5. **媒体元数据存储**：`MediaAsset` 持久化到 MongoDB，记录 originUrl、cdnUrl、thumbnailUrl、width、height、durationMs、fileSizeBytes、mimeType、clientMeta 等
6. **可观测性**：上传/下载操作接入 `IOAccessLogger`，文件大小、耗时、成功率等指标
7. **治理**：OSS 调用使用 `governance.Retry` + `CircuitBreaker`
8. **错误处理**：使用已有 `ModuleOSS`、`ModuleCDN` 的 `AppError` 体系
9. **端侧 Media SDK**：提供统一的 `MediaUploadManager`（队列、重试、离线队列）和 `MediaDownloadCache`（下载、本地缓存）

## 不做什么（Out of Scope）

- 不实现媒体处理管线（转码、缩略图生成、波形提取）——端侧提取或后续独立 Phase
- 不实现实时流媒体传输（WebRTC）——属于 realtime-gateway + RTC 独立特性
- 不实现 CDN 边缘计算或智能路由
- 不实现媒体审核管线（内容安全）——后续独立特性
- 不实现多云 OSS 自动切换（当前单一供应商）

## 约束

### 技术约束

- 必须遵循 runtime 模块模式：接口 + 实现 + observability + governance
- 必须使用 `RuntimeConfigProvider` 读取 OSS/CDN 配置，禁止硬编码
- 必须使用 `runtime/errors.AppError` 体系（`ModuleOSS`、`ModuleCDN`）
- OSS 适配器仅允许在 `runtime/media/` 内部，领域服务禁止直接 import OSS SDK
- presigned URL 有效期默认 15 分钟，可配置
- 端侧上传必须通过 `MediaUploadManager`，禁止 UI 层直接调用 OSS

### 业务约束

- messaging 类别文件大小上限 50MB，content 类别上限 500MB
- 语音消息 AAC (m4a) 编码，最大 120 秒（可配置）
- 图片格式白名单：JPEG、PNG、WebP、GIF
- 视频格式白名单：MP4、MOV
- 音频格式白名单：AAC/M4A

### 部署约束

- `runtime/media` 作为 Go module，被各服务进程 import，不独立部署
- OSS bucket 按环境隔离：dev、integration、prod 各自独立 bucket
- CDN 域名按环境配置

### 弱网与性能约束

- 端侧上传支持断点续传（presigned URL 过期后自动重新获取）
- 弱网（<100kbps）下上传超时时间延长至 120 秒
- 上传失败自动重试 3 次，指数退避（1s→2s→4s）
- 并发上传限制：同时最多 3 个上传任务
- CDN URL 响应要求 P99 < 200ms（强网）

## 适用范围与约束

- **适用场景**：所有需要持久化存储的媒体文件（图片、视频、音频、文档），不适用于实时流媒体
- **前置条件**：OSS 供应商已选定并配置、CDN 域名已备案
- **不适用**：WebRTC 实时音视频流、临时文件（不需持久化的场景）

## 对标输入与吸收结论

| 对标 | 借鉴点 | 不借鉴点 | 适用边界 |
|------|--------|---------|---------|
| 微信媒体上传 | 分片上传、断点续传、弱网重试 | 自研 CDN 基础设施 | 体量差异大，复用云厂商 CDN |
| AWS S3 SDK | presigned URL 模式、multipart upload | 过于复杂的分片管理 | 单文件 ≤500MB 用 presigned PUT 即可 |
| 七牛云/又拍云 | 上传策略（token 包含限制条件） | 供应商锁定 | 保持 OSS 适配器可替换 |
| Telegram 媒体上传 | 小文件快速通道（<10MB 直传） | 自建文件集群 | 消息媒体适用快速通道 |

## 验收重点

- A1: MediaStore 接口完整性（CRUD + 策略校验）
- A2: OSS presigned URL 上传端到端可用
- A3: CDN URL 签名与过期策略正确
- A4: 上传策略按 Category × MediaType 生效
- A5: 弱网场景下上传重试与恢复
- A6: 可观测性指标与日志完整
- A7: content-service 迁移到 MediaStore 接口
- A8: 端侧 MediaUploadManager 队列、重试、离线队列

详细验收标准见 `acceptance.yaml`。
