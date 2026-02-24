# 开发任务：runtime-learning

- [x] 设计：Event/Scorecard struct + Recorder interface → `runtime/learning/learning.go`
- [x] 实现：NoopRecorder（无操作默认值） → `runtime/learning/learning.go`
- [x] 实现：BufferedRecorder（periodic flush + size flush） → `runtime/learning/learning.go`
- [x] 实现：LogSink（日志输出 sink） → `runtime/learning/learning.go`
- [x] 实现：Scorecard 聚合（效果评估指标） → `runtime/learning/learning.go`
- [x] 实现：Event 结构化写入 → `runtime/learning/learning.go`
- [x] 测试：事件写入契约测试 → `runtime/learning/learning_test.go` (6 tests)
- [x] 测试：Scorecard 聚合正确性测试 → `runtime/learning/learning_test.go`
- [x] gate：集成到 make gate
