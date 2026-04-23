# 对象标识与 URL 规范

## 1. 目标

统一全系统的媒体对象引用方式，避免业务服务直接依赖 OSS/COS 的外显 URL 作为主数据。

## 2. 统一对象标识

推荐所有媒体类对象统一使用 `AssetRef`：

- `assetId`
- `provider`
- `bucket`
- `objectKey`
- `cdnDomain`
- `assetKind`
- `ownerType`
- `ownerId`
- `version`
- `checksum`
- `variants`

## 3. 规范定义

### 3.1 assetKind

建议首批支持：

- `avatar_user`
- `avatar_group`
- `image_chat`
- `image_post`
- `video_chat`
- `video_post`
- `voice_chat`
- `file_chat`

### 3.2 ownerType

建议首批支持：

- `user`
- `conversation`
- `message`
- `post`
- `circle`

## 4. 数据库存储原则

业务表中优先存：

- `assetId`
- `version`

允许冗余存：

- `cdnUrlSnapshot`

但 `cdnUrlSnapshot` 不能作为唯一真相源。

## 5. objectKey 规范

统一格式：

```text
{domain}/{assetKind}/{yyyy}/{mm}/{dd}/{ownerType}/{ownerId}/{assetId}_{variant}.{ext}
```

示例：

```text
user/avatar_user/2026/04/23/user/u_123/ma_100_origin.webp
chat/avatar_group/2026/04/23/conversation/c_888/ma_200_grid128.webp
content/video_post/2026/04/23/post/p_456/ma_300_origin.mp4
```

## 6. CDN URL 规范

统一外显形式：

```text
https://{cdnDomain}/{objectKey}?v={version}
```

原则：

- `v` 用于缓存失效与版本切换
- 公开资源使用 CDN URL
- 私有资源可在运行时生成签名 URL

## 7. 版本规则

- 头像变更必须递增 `version`
- 群头像重算成功必须递增 `version`
- 派生规格变化导致渲染结果变化时，应提升 `version` 或 `variantVersion`

## 8. 厂商适配规则

runtime 统一暴露：

- `BuildObjectKey()`
- `BuildPublicURL()`
- `BuildSignedURL()`

业务服务不得自己拼接 OSS/COS URL。

## 9. 禁止项

- 业务表直接保存临时签名 URL 作为主字段
- 业务逻辑硬编码厂商域名
- 客户端直接拼 objectKey
