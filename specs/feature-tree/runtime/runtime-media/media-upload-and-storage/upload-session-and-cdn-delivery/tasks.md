# 上传会话与 CDN 分发 任务列表

> L4 Story 工程执行清单。详细任务编号引用 L2 `runtime-media` tasks.md。

## 当前交付任务

### Go 接口与实现
- [x] G1: runtime/media/media.go — 接口 + 类型定义
- [x] G2: runtime/media/media_policy.go — 策略引擎
- [x] G3: runtime/media/oss_adapter.go — OSS presigned URL 实现
- [x] G4: runtime/media/cdn.go — CDN URL 签名
- [x] G5: runtime/media/mock.go — MockMediaStore
- [x] G7: 可观测性接入（IOAccessLogger）
- [x] G8: 治理接入（Retry + CircuitBreaker）

### Dart SDK
- [x] D1: media_asset_dto.dart
- [x] D2: upload_policy.dart
- [x] D3: media_upload_manager.dart
- [x] D4: media_download_cache.dart
- [x] D5: Provider 注册

### 测试
- [x] T1: Go MockMediaStore 单测
- [x] T2: 策略引擎单测

## 搁置任务

- [ ] G6: content-service 迁移（重启条件：content-service codegen 修复后）
- [ ] T3: content-service 迁移回归（重启条件：G6 完成后）
- [ ] T4: Dart MediaUploadManager 单测（重启条件：T2 测试基础设施就绪后）
- [ ] T5: Dart MediaDownloadCache 单测（重启条件：T2 测试基础设施就绪后）

见 L2 tasks.md。

## 未来演进任务

见 L2 tasks.md。
