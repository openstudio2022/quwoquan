# 统一媒体运行时 任务列表

## 当前交付任务

- [x] M1: [metadata] 无需新建 metadata（runtime/media 是基础设施模块，非 DDD 实体）；但需更新 content/post/service.yaml 说明媒体 API 由 MediaStore 驱动
- [x] C1: [codegen] 无 codegen 产物（runtime/media 为手写接口 + 实现）
- [x] G1: [Go] 创建 `runtime/media/media.go` — MediaStore 接口 + InitUploadOpts + UploadSession + MediaAsset + MediaCategory 类型定义
- [x] G2: [Go] 创建 `runtime/media/media_policy.go` — UploadPolicy 结构 + DefaultPolicies 按 Category×MediaType 映射 + ValidateUpload 校验函数
- [x] G3: [Go] 创建 `runtime/media/oss_adapter.go` — OSSMediaStore 实现（presigned URL 生成、CompleteUpload→CDN URL、MongoDB MediaAsset 持久化）
- [x] G4: [Go] 创建 `runtime/media/cdn.go` — CDN URL 签名函数（带过期时间 + 密钥）
- [x] G5: [Go] 创建 `runtime/media/mock.go` — MockMediaStore 实现（用于单元测试和 dev 环境）
- [x] G7: [Go] 可观测性接入 — IOAccessLogger 记录每次 Init/Complete/Abort 操作
- [x] G8: [Go] 治理接入 — OSS 调用包装 governance.Retry + CircuitBreaker
- [x] D1: [Dart] 创建 `lib/cloud/media/media_asset_dto.dart` — MediaAssetDto（与云侧 MediaAsset 对齐）
- [x] D2: [Dart] 创建 `lib/cloud/media/upload_policy.dart` — 端侧策略校验（预校验，避免无效上传）
- [x] D3: [Dart] 创建 `lib/cloud/media/media_upload_manager.dart` — 上传队列 + 并发限制 + 重试 + 离线 Hive 队列 + 网络恢复
- [x] D4: [Dart] 创建 `lib/cloud/media/media_download_cache.dart` — LRU 缓存 + 下载队列 + 流式访问
- [x] D5: [Dart] 在 `app_providers.dart` 注册 mediaUploadManagerProvider 和 mediaDownloadCacheProvider
- [x] T1: [测试-Go] runtime/media MockMediaStore 单元测试（Init/Complete/Abort/Get 正常+异常路径）
- [x] T2: [测试-Go] 策略引擎单元测试（各 Category×MediaType 组合、超限拦截）

## 搁置任务（不在本次交付范围）

- [ ] G6: [Go] content-service 迁移 — PostService 中 6 个媒体 API 替换为 MediaStore 调用（重启条件：content-service codegen 修复后）
- [ ] T3: [测试-Go] content-service 迁移后契约测试不变 回归验证（重启条件：G6 完成后）
- [ ] T4: [测试-Dart] MediaUploadManager 单元测试 队列、并发、重试、离线、恢复（重启条件：T2 widget 测试基础设施就绪后）
- [ ] T5: [测试-Dart] MediaDownloadCache 单元测试 缓存命中、LRU 淘汰、下载失败（重启条件：T2 widget 测试基础设施就绪后）
- [ ] 媒体处理管线（转码/缩略图/波形）（重启条件：content 域需要视频转码时）
- [ ] 多云 OSS 适配器（重启条件：业务需多云部署时）
- [ ] OSS 生命周期管理（重启条件：运维基础设施就绪后）
- [ ] 媒体审核管线（重启条件：内容安全供应商对接后）

## 未来演进任务

- [ ] 分片上传 multipart（对应 design KD-3 演进方向）
- [ ] CDN 智能路由（对应 design 未来演进 4）
- [ ] circle-service 迁移到 MediaStore（当前 FileStore 保留，后续统一）
