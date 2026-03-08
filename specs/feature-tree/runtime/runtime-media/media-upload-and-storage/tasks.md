# 媒体上传与存储 任务列表

> 任务继承自父节点 `runtime-media` tasks.md，此处为 L3 视角的任务汇总。

## 当前交付任务

- [x] G1-G5, G7-G8: [Go] MediaStore 接口 + OSS 适配器 + 策略引擎 + CDN + Mock + 可观测 + 治理（详见父节点）
- [x] D1-D5: [Dart] MediaAssetDto + UploadPolicy + MediaUploadManager + MediaDownloadCache + Provider 注册（详见父节点）
- [x] T1-T2: [测试] Go MockMediaStore 单测 + 策略引擎单测（详见父节点）

## 搁置任务

- [ ] G6: content-service 迁移（重启条件：content-service codegen 修复后，详见父节点）
- [ ] T3: content-service 迁移回归测试（重启条件：G6 完成后）
- [ ] T4-T5: Dart MediaUploadManager/DownloadCache 单测（重启条件：T2 测试基础设施就绪后）

见父节点。

## 未来演进任务

见父节点。
