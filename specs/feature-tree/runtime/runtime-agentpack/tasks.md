# 开发任务：runtime-agentpack

- [x] 设计：TaskPack schema（FeatureInfo/MetadataRef/Deliverable/TestRef/Acceptance） → `runtime/agentpack/types.go`
- [x] 实现：ScanFeatureTree — 递归扫描特性树 + 状态推断 → `runtime/agentpack/tree_index.go`
- [x] 实现：WriteIndex / ReadIndex — YAML 序列化 → `runtime/agentpack/tree_index.go`
- [x] 实现：SearchFeatures — 关键词匹配搜索 → `runtime/agentpack/tree_index.go`
- [x] 实现：IngestTaskPack — 新特性归档到特性树 → `runtime/agentpack/tree_index.go`
- [x] 测试：ScanFeatureTree 目录扫描 + 状态推断 → `runtime/agentpack/agentpack_test.go`
- [x] 测试：SearchFeatures 多场景搜索 → test
- [x] 测试：WriteIndex/ReadIndex 序列化往返 → test
- [x] 测试：IngestTaskPack 归档 → test
- [x] gate：go vet + go test 全量通过
