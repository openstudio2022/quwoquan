# L2 特性：runtime-agentpack

## 功能说明
- ScanFeatureTree：按 `AppRoot -> L1_domain_service -> L2_business_capability -> L3_story` 扫描目录并构建 TreeIndex。
- WriteIndex / ReadIndex：tree_index.yaml 序列化/反序列化。
- SearchFeatures：关键词搜索特性树（按 ID/名称/标签匹配）。

## 约束
- TreeIndex 只表达正式特性树结构；短期 Task 不进入索引，也不从树内计划文件推断状态。
- tree_index.yaml 为自动生成，不手写。

## 验收标准
- A1：扫描目录 → 自动构建正确的特性树索引。
- A1：搜索特性树「推荐」→ 返回匹配的 recommendation 特性。
- A8：全链路自动化测试（扫描、搜索、索引写入与读取）。
