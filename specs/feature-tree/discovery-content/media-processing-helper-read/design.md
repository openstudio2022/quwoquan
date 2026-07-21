# 媒体处理与辅助读取设计

## 设计动因

图片和视频上传完成后都会产生 `MediaAsset(processing)`。没有生产消费者时，发布必然被
`media_not_ready` 永久阻断；未经验证的原始图片或视频也不得直接公开，因此媒体处理不是
离线优化，而是 Post 发布前的强依赖生命周期。

## 模块与调用链

```text
CompleteMediaUpload
  → MediaAssetCreated + media outbox（同事务）
  → processing.Worker（checkpoint，至少一次）
  → FFmpegMediaProcessor
       GetObject(private CAS)
       → image: real decode + pixel/dimension guard + normalized JPEG/PNG
       → video: ffprobe + H.264/AAC MP4 + fast-start + 2s GOP
       → video cover.jpg + preview sprites + manifest
       → PutObject(versioned public slices)
  → RecordMediaProcessingResult(ready|rejected)
  → GetMediaAsset / Post media binding / preview-track read
```

## 分层

- `internal/application/media/processing`：只编排事实、状态、幂等、checkpoint 与恢复语义。
- `internal/infrastructure/content/media/processing`：对象存储、FFmpeg/FFprobe、manifest
  编码与 Prometheus observer。
- `internal/domain/media`：`MediaAsset` 状态机与 ready descriptor 不变量。
- `cmd/api`：显式装配 Worker、健康检查和进程生命周期。

该边界允许今后独立部署：保留 application Worker，替换 outbox/checkpoint adapter 与
`ResultRecorder` 为内部 HTTP 客户端即可；当前不创建第二个服务进程或第二套状态机。

## 一致性与恢复

- outbox 读取后先处理、再保存 checkpoint；失败事实保持可重放。
- 回写幂等键只由 `eventId` 派生，跨重启稳定。
- 已离开 `processing` 的资产在重放时直接 no-op。
- 内容性错误（无视频流、不可解码、超时长）写 `rejected` 后推进 checkpoint。
- 对象存储、FFmpeg 运行时和持久化错误不改变聚合终态，不推进 checkpoint。
- 有有效 `checkpoint` 但缺少 `aggregateId` 或无法恢复 MediaAsset 快照的源事实，先按
  `(consumer,eventId)` 幂等写入 `media_processing_dead_letters`，只保存身份、cursor 和
  稳定原因，不保存 payload；死信写成功后才能推进 checkpoint，写失败仍保持可重放。
- 缺少 eventId 或 checkpoint 的 source cursor 不可安全跳过，Worker 必须 fail-closed 并
  触发 health/poison 指标，而不是伪造 checkpoint。
- 派生 slice 使用 `assetId/processingVersion` 路径，重处理不覆盖旧版本。`processingVersion`
  在 ready/rejected 处理终态写入时冻结；封面选择和 access policy 等命名状态迁移只推进
  aggregate version，读取/恢复时仍按 processingVersion 校验 descriptor，不能因后续
  写入将合法的既有 slice 误判为失效。

## 交付策略

首发播放契约只包含 progressive fast-start MP4。metadata 不登记 adaptive profile/flag；
在 ABR 打包、播放器和 QoE 证据共同完成前，不得对外宣称 HLS/DASH 已交付，也不得把原始
上传字节作为 ready fallback。图片公开切片必须从处理器生成的 normalized object
物化，禁止从原始上传 CAS 复制。

## 图片交付 descriptor 与 variants

图片 variants 的设计真相源是 L3 `image-delivery-variants`：`MediaAsset` 继续是唯一
aggregate，处理器在同一 ready transaction 写入 `ImageDeliveryDescriptor`
（normalized baseline、公共 slice、宽高、MIME、dominantColor、LQIP、contentProfile、
processingVersion、derivativePolicyVersion）。`thumbnail/display/cover/full` 是同一 baseline
的 CDN delivery profile，不创建 `MediaAssetVariant`、variant Store 或第二状态机。

`ImageVariantPolicy` 从 `content/media_asset` metadata 生成到 Service、Data 与 App URL
resolver；删除 Post metadata、Python 与 App 内的重复尺寸/质量常量。策略升级通过新的
processingVersion 产生、读取并校验新 descriptor 后原子切换，失败或回滚持续服务旧
descriptor，不能按 aggregate version 误判既有 slice。

`RequestOriginalImageAccess` 由 `MediaOriginalAccessFact` 记录 append-only 审计。授权必须
同时查询 asset policy 与 Post named visibility reader；非可见 persona 为 403、超出
`viewerPersonaId + mediaId + purpose` 窗口为 429。业务层不直连 Post persistence，且
不会把 owner-only `GetMediaAsset` 当作内容可见性判定。

## SLO、观测与回滚

- Worker scan 健康超过 15 分钟未成功即不健康。
- 记录 jobs result、全链路任务时长、每次扫描返回数量、连续满批、poison event、
  poison dead-letter 写入失败和 `RecordMediaProcessingResult` operation SLO。
- 50 MiB、最长 1 小时视频的全链路 job P95 预算为 840 秒（15 分钟 job timeout 前的
  告警边界）；基础设施错误或失败率持续 10 分钟为 critical，连续满批 15 分钟为 warning，
  任何 poison event 为 critical。
- 回滚只允许停止新上传/发布并保留 outbox 重放；已生成 versioned slice 和已发布 Post
  继续可读，禁止把 `processing` 强改为 `ready`。
