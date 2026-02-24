# 开发任务：runtime-observability

**实现状态：95% COMPLETE** (~1,800 行代码，22 个文件，8 个测试文件)

- [x] 实现：IOAccessLog/ExceptionLog/ProcessTraceLog 日志结构
- [x] 实现：IOAccessLogger/ExceptionLogger/ProcessTraceLogger
- [x] 实现：HTTPServerMiddleware（入站 HTTP 中间件）
- [x] 实现：LoggedRoundTripper（出站 HTTP 客户端）
- [x] 实现：WrapMQConsumer/WrapMQPublisher（MQ 中间件）
- [x] 实现：NewObservedHTTPClient（重试 + 日志）
- [x] 实现：8 个服务专用客户端工厂
- [x] 实现：SinkRouter/KVMetadataFilter/CorrelationMeta
- [x] 实现：NewHTTPServerMiddleware wrapper（P0-fix-1 修复）
- [x] 测试：8 个测试文件覆盖中间件/过滤/关联上下文
- [ ] 实现：OTEL exporter adapter（L4）
- [ ] 实现：dashboard/alert template binding（L5）
- [ ] 实现：contract sync 与 SLI binding（L5）
- [ ] gate：集成到 make gate
