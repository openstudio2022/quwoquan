# 开发任务：runtime-experiments

- [x] 设计：Assignment struct + Resolver interface → `runtime/experiments/experiments.go`
- [x] 实现：StaticResolver（默认 bucket fallback） → `runtime/experiments/experiments.go`
- [x] 实现：HashResolver（consistent hashing 确定性分桶） → `runtime/experiments/experiments.go`
- [x] 实现：Experiment 注册 + 分桶解析 → `runtime/experiments/experiments.go`
- [x] 实现：灰度百分比计算 + 确定性 hash → `runtime/experiments/experiments.go`
- [x] 实现：fallback + rollback 策略 → `runtime/experiments/experiments.go`
- [x] 测试：分桶确定性测试 → `runtime/experiments/experiments_test.go` (7 tests)
- [x] 测试：缓存命中/失效测试 → `runtime/experiments/experiments_test.go`
- [x] gate：集成到 make gate
