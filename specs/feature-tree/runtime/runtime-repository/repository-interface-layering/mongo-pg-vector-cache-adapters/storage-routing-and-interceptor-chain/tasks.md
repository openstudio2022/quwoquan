# 开发任务：storage-routing-and-interceptor-chain

- [ ] 实现：RepositoryFactory 根据 EntityRegistry.GetStorageBackend 路由
- [ ] 实现：缓存叠加逻辑（cache_enabled 时包装 Redis 中间件）
- [ ] 实现：Repository 拦截链（span、metric、慢查询、超时）
- [ ] 集成：runtime-config 连接池、慢查询阈值、超时配置
- [ ] 集成：runtime-observability OTEL span/metric 绑定
- [ ] 测试：存储工厂路由正确性测试（各 storage_backend 组合）
- [ ] 测试：拦截链集成测试（span、metric、慢查询）
- [ ] gate：集成到 make test-contract + make gate
