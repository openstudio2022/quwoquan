# 存储、CDN 与云厂商适配

## 1. 目标

统一支持阿里云 OSS、腾讯云 COS 等对象存储，并保持业务层无感。

## 2. 适配抽象

建议 runtime 统一暴露：

- `InitUpload`
- `CompleteUpload`
- `AbortUpload`
- `DeleteObject`
- `HeadObject`
- `BuildPublicURL`
- `BuildSignedURL`

## 3. 推荐部署形态

### 3.1 对象存储

- 阿里云 OSS
- 腾讯云 COS

### 3.2 CDN

- 阿里云 CDN
- 腾讯云 CDN / EdgeOne

### 3.3 原则

- 对外只暴露 CDN 域名
- 对内保存 provider + bucket + objectKey
- 不把源站 URL 暴露给客户端

## 4. 存储组织建议

### 方案 A：一桶多前缀

适合早期阶段：

- `avatars/users/`
- `avatars/groups/`
- `images/chat/`
- `images/content/`
- `videos/chat/`
- `videos/content/`

### 方案 B：按热度或类型拆桶

适合中后期：

- `hot-avatar-bucket`
- `image-bucket`
- `video-bucket`

## 5. 云厂商差异屏蔽

屏蔽项包括：

- presign 生成方式
- 私有读写策略
- 图片处理参数
- CDN 签名算法
- 生命周期规则 API

## 6. 推荐策略

- 首期选定一个主云厂商
- runtime 代码保持双实现接口
- 配置层决定当前启用的 provider
