# Media 客户端与服务端契约

## 1. 原则

- 客户端不感知 OSS/COS 细节
- 客户端不拼接 objectKey
- 服务端统一返回可消费的媒体引用

## 2. 上传初始化返回

至少包含：

- `sessionId`
- `uploadUrl` / `presignUrl`
- 可选 `mediaId`

与现有 `ContentMediaInitUploadResponse` 保持一致并逐步扩展。

## 3. 上传完成返回

建议统一返回：

- `assetId`
- `cdnUrl`
- `version`
- `variants`

## 4. 头像读取

客户端应优先消费：

- `avatarAssetId`
- `avatarUrl`
- `avatarVersion`

其中 `avatarUrl` 可作为服务端派生字段返回。

## 5. 群头像读取

客户端应消费：

- `avatarUrl`

`groupAvatarVersion`、`groupAvatarAssetId`、`groupAvatarSourceHash` 是服务端内部资产与幂等字段；客户端不得把旧群头像 URL 字段或成员头像列表作为群头像主渲染输入。

## 6. 失败策略

- 读取失败：展示通用图片加载错误态并记录诊断
- 派生未完成：服务端保留上一版；新群无上一版时不得下发空 `avatarUrl`
- 上传失败：允许重试
