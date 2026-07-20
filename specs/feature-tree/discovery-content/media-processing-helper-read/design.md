# 媒体处理与辅助读取设计

## 设计动因

视频上传完成后会产生 `MediaAsset(processing)`。没有生产消费者时，发布必然被
`media_not_ready` 永久阻断，因此媒体处理不是离线优化，而是 Post 发布前的强依赖生命周期。

## 模块与调用链

```text
CompleteMediaUpload
  → MediaAssetCreated + media outbox（同事务）
  → processing.Worker（checkpoint，至少一次）
  → FFmpegVideoProcessor
       GetObject(private CAS)
       → ffprobe
       → H.264/AAC MP4 + fast-start + 2s GOP
       → cover.jpg
       → preview sprites + manifest
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
- 派生 slice 使用 `assetId/version` 路径，重处理不覆盖旧版本。

## 交付策略

首发播放契约为 progressive fast-start MP4。metadata 中的 adaptive profile 必须受
`enable_video_adaptive_streaming=false` 保护；在 ABR 打包、播放器和 QoE 证据共同完成前，
不得对外宣称 HLS/DASH 已交付，也不得把原始上传字节作为 ready fallback。

## SLO、观测与回滚

- Worker scan 健康超过 15 分钟未成功即不健康。
- 记录 jobs result、单任务处理时长、连续满批和回写 operation SLO。
- 基础设施错误持续 10 分钟为 critical；连续满批 15 分钟为 warning。
- 回滚只允许停止新上传/发布并保留 outbox 重放；已生成 versioned slice 和已发布 Post
  继续可读，禁止把 `processing` 强改为 `ready`。
