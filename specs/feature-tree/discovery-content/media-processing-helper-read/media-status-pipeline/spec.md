# L3 Story：媒体处理状态流水线

## 用户故事

作为发布视频的创作者，我希望上传完成后视频能可靠进入处理中并自动变为可发布资产，
以便发布链只绑定真实可播放的媒体，而不是假 `ready` 或原始上传字节。

## 功能边界

- `MediaUploadSession completed` 同事务创建 `MediaAsset(processing)` 与 outbox 事实。
- Worker 消费事实并生成标准化视频、封面、缩略图/预览轨道。
- ready descriptor 必须包含 codec/container/尺寸/时长/音频、公开 slice 与预览 manifest。
- Post 绑定只接受 owner 匹配且 `ready` 的 MediaAsset。

## 验收标准

- 带音轨与无音轨视频都生成 H.264/AAC fast-start MP4；无音轨输入补静音 AAC。
- 真实对象存储中的派生对象可读，数据库中的 slice key 与探测结果一致。
- 发布照片仍直接 `ready`，且只携带 MediaAsset ID，不携带本地路径或临时 URL。
- 同一事实重复投递不会重新处理已终态资产。
