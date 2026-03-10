# 视频消息端到端 设计方案

> 详细方案对比与关键决策见 L3 `../design.md`。本文仅记录 Story 级补充。

## 设计动因

实现视频消息从选择→压缩→上传→发送→接收→播放的完整链路。复用语音消息已验证的 MediaUploadManager、MediaDownloadCache、Message.media 字段模型。

## 上游输入评审

- L3 spec.md F1 (1-9) 明确，约束充分
- L3 acceptance.yaml A1~A4 可测量

## 选型决策

| 组件 | 选定 | 理由 |
|------|------|------|
| 视频压缩 | `video_compress` | 轻量原生、包体积小、720p 枚举 |
| 封面提取 | `video_compress.getFileThumbnail` + `video_thumbnail` | 双重保障 |
| 视频播放 | `chewie` + `video_player`（已安装） | 零新增依赖 |
| 缩略图展示 | `CachedNetworkImage`（已安装） | 网络缓存 |
| 视频缓存 | 独立 `MediaDownloadCache` 500MB LRU | 隔离语音/文件缓存 |

## 关键设计决策

- KD-2: 视频压缩与封面提取流程（见 L3 design.md）
- KD-3: 视频消息气泡设计（见 L3 design.md）
- KD-10: 视频缓存独立池（见 L3 design.md）

## 适用场景与约束

- 视频 ≤100MB、≤10 分钟、mp4/mov
- 非 WiFi 不自动下载
- 低端设备压缩可能较慢（>5s for 4K→720p）

## 未来演进

- 云端视频转码（统一格式/码率）
- 视频分片断点续传
- 视频封面 GIF 预览
- 非 WiFi 自适应压缩策略
