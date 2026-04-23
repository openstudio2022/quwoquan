# 资产模型与归属

## 1. 总原则

媒体对象的“业务归属”与“底层托管”必须分离。

- 业务归属决定谁维护主语义、谁触发更新
- 底层托管决定文件如何上传、存储、分发、签名

## 2. 归属矩阵

### 2.1 用户头像

- 业务归属：`user-service`
- 主字段：`avatarAssetId`、`avatarVersion`
- 触发事件：`UserAvatarUpdated`

### 2.2 群头像

- 业务归属：`chat-service`
- 主字段：`groupAvatarAssetId`、`groupAvatarVersion`、`groupAvatarSourceHash`
- 触发事件：`ConversationAvatarUpdated`

### 2.3 聊天媒体

- 业务归属：`chat-service`
- 主字段：消息上的 `mediaAssetIds`

### 2.4 内容图片/视频

- 业务归属：`content-service`
- 主字段：`coverAssetId`、`mediaAssetIds`

## 3. 统一资产主模型

建议 `MediaAsset` 扩展为：

- `assetId`
- `category`
- `assetKind`
- `ownerType`
- `ownerId`
- `provider`
- `bucket`
- `objectKey`
- `version`
- `variants`
- `metadata`

## 4. runtime 的职责

runtime 负责：

- 统一 `MediaAsset` 结构
- 统一 object key / URL 构建
- 统一存储和 CDN 适配

业务服务负责：

- 谁拥有该资产
- 何时绑定、解绑、失效
- 哪个版本是当前生效版本
