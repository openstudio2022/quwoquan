# 开发任务：runtime-interceptor

- [x] 设计：读链/写链中间件接口定义（Chain + InterceptedRepository） → `runtime/interceptor/interceptor.go`
- [x] 实现：读链 — APIExposureInterceptor 字段过滤（drop/readonly/readwrite） → `runtime/interceptor/api_filter.go`
- [x] 实现：读链 — LogMaskingInterceptor 脱敏（PII→mask, SECRET→drop, SENSITIVE→mask_partial） → `runtime/interceptor/log_masking.go`
- [x] 实现：读链 — AuditInterceptor 审计日志 → `runtime/interceptor/audit.go`
- [x] 实现：写链 — NOT_NULL 必填校验 → `runtime/interceptor/interceptor.go`
- [x] 实现：写链 — 类型约束校验 → `runtime/interceptor/interceptor.go`
- [x] 实现：写链 — 领域事件发布 hook → `runtime/interceptor/interceptor.go`
- [x] 实现：写链 — observe_metric 指标自动产生 → `runtime/interceptor/interceptor.go`
- [x] 集成：拦截链注入 Repository 层 → `runtime/repository/factory.go`
- [x] 测试：读链单元测试（SECRET/PII/PUBLIC 全场景） → `runtime/interceptor/interceptor_test.go`
- [x] 测试：写链单元测试（必填/事件/指标全场景） → `runtime/interceptor/interceptor_test.go`
- [x] 测试：端到端契约测试（UserProfile PII + Post 事件 hook） → `runtime/interceptor/interceptor_test.go`
- [x] gate：集成到 make gate
