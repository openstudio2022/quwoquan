# 开发任务：runtime-sli

- [x] 设计：Indicator + Objective + DataPoint + Report + KnowledgeEntry 类型 → `runtime/sli/types.go`
- [x] 实现：Collector — 指标注册/查询/列表 → `runtime/sli/collector.go`
- [x] 实现：Record / RecordBatch — 数据点持久化 → `runtime/sli/collector.go`
- [x] 实现：GenerateReport — 时间窗口聚合 + SLO 达标判定 → `runtime/sli/collector.go`
- [x] 实现：LearnFromReport — Report → KnowledgeEntry upsert → `runtime/sli/collector.go`
- [x] 实现：QueryKnowledge — 按 feature 搜索历史效果 → `runtime/sli/collector.go`
- [x] 实现：computeSummary — count/sum/mean/percentile 统计 → `runtime/sli/collector.go`
- [x] 实现：evaluateObjective — SLO 达标判定（<=/>=/</>） → `runtime/sli/collector.go`
- [x] 测试：computeSummary 正常/空值 → `runtime/sli/sli_test.go`
- [x] 测试：percentile 准确性 → test
- [x] 测试：evaluateObjective 各操作符 → test
- [x] 测试：指标注册/列表/查询 → test
- [x] gate：go vet + go test 全量通过
