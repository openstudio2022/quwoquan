# 开发任务：embedded-pg-testcontainers-miniredis

- [ ] 实现：pg_suite.go — embedded-postgres 启动/关闭
- [ ] 实现：pg_suite — migration 执行
- [ ] 实现：pg_suite — truncate 清理
- [ ] 实现：mongo_suite.go — testcontainers mongo 启动/关闭
- [ ] 实现：mongo_suite — 索引创建
- [ ] 实现：mongo_suite — cleanup
- [ ] 实现：redis_suite.go — miniredis 启动/关闭
- [ ] 实现：redis_suite — flush/时间控制
- [ ] 实现：event_spy.go — EventPublisher spy
- [ ] 测试：pg_suite 自测（启动/CRUD/清理）
- [ ] 测试：mongo_suite 自测（启动/CRUD/清理）
- [ ] 测试：redis_suite 自测（SET/GET/TTL）
- [ ] 测试：event_spy 自测（捕获/断言）
- [ ] gate：集成到 make gate
