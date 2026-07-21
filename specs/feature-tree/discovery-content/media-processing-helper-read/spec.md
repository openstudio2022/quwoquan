# L2 业务能力：媒体处理与辅助读取

## 用户价值

用户上传图片或视频后，系统必须把私有原始字节可靠推进为经过受信验证、可发布的
`MediaAsset`；图片交付归一化基线，视频交付可播放、可预览基线，并让处理中、成功和
不可恢复失败都具有确定终态；不得依赖 fixture、原始上传 fallback 或人工伪造 `ready`。

## 范围

- `MediaUploadSession completed → MediaAsset processing → ready/rejected` 状态闭环。
- 消费 `content.media_asset.created` 耐久 outbox，按 checkpoint 至少一次处理。
- 图片真实解码、像素/尺寸守卫、方向归一与 JPEG/PNG 交付基线生成。
- `image-delivery-variants` 以 MediaAsset owned descriptor 绑定唯一 ImageVariantPolicy；
  thumbnail/display/cover/full 由 CDN profile 派生，原图访问按 Post 可见性授权。
- ffprobe 探测、H.264/AAC progressive fast-start MP4 归一、封面和预览轨道生成。
- 基础设施故障不推进 checkpoint；内容损坏进入 `rejected` 并记录稳定原因。
- 带有效 cursor 的损坏 outbox 元数据或无法恢复的资产快照先持久化到
  `media_processing_dead_letters`，再推进 checkpoint；原始 payload 不得进入死信记录。
- `GetMediaAsset`、交付引用和预览轨道读取只暴露权威处理结果。
- Worker 健康、全链路耗时、失败率、连续满批和 poison event 可观测。

## 不在本能力内

- Post 发布事务、审核和作者结果回流归 `publish-comment-reaction`。
- 播放器 QoE 归 `runtime/runtime-media`。
- HLS/DASH ABR 不属于首发交付契约；metadata 不登记未实现的 adaptive profile/flag，
  首发唯一播放主线是已验证的 progressive fast-start MP4。

## 架构约束

- Worker 集成在 `content-service`，但作为独立功能模块，仅依赖
  `OutboxSource / AssetSnapshotLoader / CheckpointStore / MediaProcessor /
  ResultRecorder / PoisonEventRecorder` 窄端口。
- 页面绑定和媒体状态以 metadata、MediaAsset 聚合与 generated contract 为唯一真相源。
- 处理结果回写必须幂等；重放不得重复改变终态。
- `processingVersion` 是 descriptor/public slice 生成时冻结的版本锚点，与可继续推进的
  MediaAsset aggregate version 分离；后续修改封面或访问策略不得按最新 aggregate
  version 重解释或使既有已验证 slice 失效。
- FFmpeg、对象存储或 checkpoint 不可用时 fail-fast/重试，禁止伪造成功或回退原视频。

## 商用验收

- 真实 MinIO + MongoDB + FFmpeg 下，`upload_policy` 允许且内容真实匹配的图片、
  带音轨和无音轨视频均可达 `ready`，损坏、伪装或超限字节可达 `rejected`。
- ready 描述符满足 codec/container/audio/fast-start/keyframe/slice/preview manifest
  全部约束，并可被 Post 发布绑定读取。
- 进程重启、checkpoint 保存失败和重复事实不会丢事件或重复处理终态资产。
- 损坏事实不会永久阻塞后续资产；死信持久化失败时 checkpoint 保持不动，避免静默跳过。
- local_contract 与 api_integration 证据路径真实存在且被 acceptance 反向绑定。
