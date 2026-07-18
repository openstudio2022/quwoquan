# 上传会话与 CDN 分发（Upload Session and CDN Delivery）

> **层级**：L3_story（隶属 L2 `runtime-media`）
> **状态**：specified

## 背景与动机

`MediaStore` 的核心交付 Story：实现三段式上传会话管理（Init→Upload→Complete/Abort）和
按媒体类型的 canonical public slice 分发，是语音消息、图片消息、视频消息、内容创作等所有
媒体上传场景的底层支撑。对象存储内部 authority、设备上传 ingress 与公开交付 authority 是
三个独立边界，业务对象不持久化临时签名 URL 或对象存储 URL。

## 目标用户

- 服务开发者：在 chat-service/content-service/circle-service 中通过 `MediaStore` 接口上传媒体
- 端侧开发者：通过 `MediaUploadManager` 管理上传队列

## 功能范围

1. **Go 接口**：`MediaStore` 接口 5 个方法（InitUpload/CompleteUpload/AbortUpload/GetAsset/BatchGetAssets）
2. **Go 实现**：内部对象存储适配器（支持华为云 OBS/S3 兼容存储）与由 upload ingress
   签发的类型化上传 ticket；端侧不得直连不可达的 storage authority
3. **Go 策略校验**：InitUpload 时按 `UploadPolicy`（Category×MediaType）校验 fileSizeBytes、durationMs、mimeType
4. **Go 持久化**：`MediaAsset` MongoDB collection，含 index on ownerId + category
5. **Go 交付**：CompleteUpload 后仅投影 `assetId + publicSliceKey`；avatar、image、video
   等公开 slice 由注入的对应 delivery base 解析，禁止使用单一 `CONTENT_CDN_DOMAIN`
   生成全部媒体类型的绝对 URL
6. **Go 可观测**：IOAccessLogger 记录每次上传操作
7. **Go 治理**：OSS 调用 Retry + CircuitBreaker
8. **Dart SDK**：`MediaUploadManager`（队列、并发限制 3、重试 3 次指数退避、离线 Hive 队列）
   只消费类型化 upload ticket 与稳定资产引用，禁止重写已签名的上传 authority
9. **Dart SDK**：`MediaDownloadCache`（LRU 200MB、本地缓存目录）
10. **Dart DTO**：`MediaAssetDto`（与云侧 MediaAsset 对齐）

## 不做什么（Out of Scope）

- 媒体处理（转码/缩略图）
- 多云切换
- CDN 域名管理和对象存储实现选型；本 Story 只消费 topology 注入的
  `storageOrigin`、`uploadIngress` 与按媒体类型区分的 `deliveryBase`

## 约束

- upload ticket 默认有效期 15 分钟，可配；其公开 authority 必须等于当前设备 target
  可达的 `uploadIngress`
- OSS bucket 按环境隔离（dev/integration/prod），只能作为服务内部 `storageOrigin`
- 并发上传限制 3 个任务
- 上传失败重试 3 次，指数退避 1s→2s→4s
- 断网时任务持久化到 Hive，网络恢复后 FIFO 恢复
- public slice 交付仅接受 HTTPS 且由 `MediaDeliveryResolver` 按媒体类型解析；Chat、Profile
  与内容投影不得绕过该边界直用 `cdnUrl`

## 适用范围与约束

- **适用**：所有需要上传到 OSS 并通过 CDN 分发的媒体文件
- **前置**：OSS 供应商配置就绪、CDN 域名已备案

## 对标输入与吸收结论

| 对标 | 借鉴 | 不借鉴 |
|------|------|--------|
| AWS S3 presigned URL | 简洁的签名上传模式 | multipart upload 分片（单文件≤500MB 不需要） |
| content-service 现有实现 | API 路由结构（init/complete/abort） | 内存 mock 实现 |

## 验收重点

详见 `acceptance.yaml`。
