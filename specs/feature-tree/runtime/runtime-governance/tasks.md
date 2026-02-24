# 开发任务：runtime-governance

- [x] 设计：ResiliencePolicy struct + PolicyProvider interface → `runtime/governance/governance.go`
- [x] 实现：StaticPolicyProvider（无操作默认值） → `runtime/governance/governance.go`
- [x] 实现：超时控制（per-service 可配置） → `runtime/governance/governance.go` (Timeout)
- [x] 实现：重试策略（指数退避 + 最大次数） → `runtime/governance/governance.go` (Retry)
- [x] 实现：熔断器（3-state 状态机：Closed/Open/HalfOpen） → `runtime/governance/governance.go` (CircuitBreaker)
- [x] 实现：限流器（令牌桶 token bucket） → `runtime/governance/governance.go` (RateLimiter)
- [x] 实现：降级开关 → `runtime/governance/governance.go`
- [x] 实现：健康检查 + 就绪检查 + 优雅关闭（L5） → `runtime/governance/governance.go`
- [x] 测试：熔断器状态转换单元测试 → `runtime/governance/governance_test.go`
- [x] 测试：限流器 QPS 边界测试 → `runtime/governance/governance_test.go`
- [x] 测试：优雅关闭集成测试 → `runtime/governance/governance_test.go` (12 tests)
- [x] gate：集成到 make gate
