# 存储、CDN 与云厂商适配

## 1. 目标

统一支持对象存储、文件根目录、本地公网 tunnel origin 与 CDN/代理层，并保持业务层无感。

## 2. 适配抽象

建议 runtime 统一暴露：

- `InitUpload`
- `CompleteUpload`
- `AbortUpload`
- `DeleteObject`
- `HeadObject`
- `BuildPublicURL`
- `BuildSignedURL`
- `AllocateSlice`
- `ResolveSliceOrigin`

## 3. 推荐部署形态

### 3.1 对象存储

- 阿里云 OSS
- 腾讯云 COS

### 3.2 CDN

- 阿里云 CDN
- 腾讯云 CDN / EdgeOne

### 3.3 原则

- 对外只暴露 CDN 域名
- 对内保存 provider / originType / bucket(or localRoot) + objectKey
- 不把源站 URL 暴露给客户端
- 切片放置以 `slice -> origin` 为最小单位，不做图片级路由表

### 3.4 临时 gamma origin

在未上正式对象存储 / CDN 前，允许 `gamma-pre` 使用：

- 本机 `media slice server`
- tunnel / 公网域名
- ECS `gamma-proxy` 回源该公网地址

该模式仅用于手工联调，不作为长期 CI 或商用拓扑。

## 4. 存储组织建议

### 方案 A：一桶多前缀 + slice

适合早期阶段：

- `media/avatar/s/avatar-seed-0001/...`
- `media/image/s/image-seed-0001/...`
- `media/video/s/video-seed-0001/...`

### 方案 B：按热度或类型拆桶

适合中后期：

- `hot-avatar-bucket`
- `image-bucket`
- `video-bucket`

不同 bucket / 文件服务器 / tunnel origin 统一由 `media slice registry` 承载：

- `sliceId`
- `originType`
- `originBaseUrl` / `localRoot`
- `publicBaseUrl`
- `healthState`
- `priority/failover`

## 5. 云厂商差异屏蔽

屏蔽项包括：

- presign 生成方式
- 私有读写策略
- 图片处理参数
- CDN 签名算法
- 生命周期规则 API
- slice 级 origin 放置与回源策略

## 6. 推荐策略

- 首期选定一个主云厂商
- runtime 代码保持双实现接口
- 配置层决定当前启用的 provider
- 节点扩容时对新 slice 使用 `consistent hashing` 或 `weighted rendezvous hashing`，避免旧 URL 大规模漂移
