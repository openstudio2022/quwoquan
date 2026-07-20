# L2 业务能力：媒体处理与辅助读取

## 用户价值

用户上传视频后，系统必须把私有原始字节可靠推进为可发布、可播放、可预览的
`MediaAsset`，并让处理中、成功和不可恢复失败都具有确定终态；不得依赖 fixture 或人工
伪造 `ready`。

## 范围

- `MediaUploadSession completed → MediaAsset processing → ready/rejected` 状态闭环。
- 消费 `content.media_asset.created` 耐久 outbox，按 checkpoint 至少一次处理。
- ffprobe 探测、H.264/AAC progressive fast-start MP4 归一、封面和预览轨道生成。
- 基础设施故障不推进 checkpoint；内容损坏进入 `rejected` 并记录稳定原因。
- `GetMediaAsset`、交付引用和预览轨道读取只暴露权威处理结果。
- Worker 健康、耗时、失败率和连续满批可观测。

## 不在本能力内

- Post 发布事务、审核和作者结果回流归 `publish-comment-reaction`。
- 播放器 QoE 归 `runtime/runtime-media`。
- HLS/DASH ABR 在 `enable_video_adaptive_streaming=false` 时不属于首发交付契约；
  首发唯一播放主线是已验证的 progressive fast-start MP4。

## 架构约束

- Worker 集成在 `content-service`，但作为独立功能模块，仅依赖
  `OutboxSource / AssetSnapshotLoader / CheckpointStore / VideoProcessor /
  ResultRecorder` 窄端口。
- 页面绑定和媒体状态以 metadata、MediaAsset 聚合与 generated contract 为唯一真相源。
- 处理结果回写必须幂等；重放不得重复改变终态。
- FFmpeg、对象存储或 checkpoint 不可用时 fail-fast/重试，禁止伪造成功或回退原视频。

## 商用验收

- 真实 MinIO + MongoDB + FFmpeg 下，带音轨和无音轨视频均可达 `ready`，损坏字节可达
  `rejected`。
- ready 描述符满足 codec/container/audio/fast-start/keyframe/slice/preview manifest
  全部约束，并可被 Post 发布绑定读取。
- 进程重启、checkpoint 保存失败和重复事实不会丢事件或重复处理终态资产。
- local_contract 与 api_integration 证据路径真实存在且被 acceptance 反向绑定。
